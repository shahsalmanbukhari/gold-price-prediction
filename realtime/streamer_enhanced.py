"""
Enhanced Real-Time Streaming Orchestrator with Provider Abstraction
Coordinates multiple providers with automatic failover
"""

import asyncio
import fcntl
import signal
from datetime import datetime, timezone
from typing import Optional
from loguru import logger
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from realtime.provider_factory import ProviderFactory
from realtime.providers.base_provider import BaseProvider, ProviderResponse
from realtime.data_handler import DataHandler
from realtime.redis_cache import get_redis_cache
from config.settings import get_settings
from realtime.training_scheduler import BackgroundTrainingScheduler
from src.database import HorizonPrediction, RetrainingRun, PredictionDecision, get_session, save_unique_price_from_response, update_provider_status
from src.horizon_prediction_service import HorizonPredictionService
from src.background_lifecycle import HeartbeatService, NotificationService, TrustService
from src.model_pipeline import ModelBundleManager


class EnhancedGoldStreamer:
    """
    Enhanced streaming orchestrator with provider abstraction

    Features:
    - Multi-provider support with automatic failover
    - Hot-swappable providers
    - Health monitoring
    - Database persistence
    - Redis caching
    - Graceful shutdown
    """

    def __init__(self, preferred_provider: Optional[str] = None, config_path: Optional[str] = None):
        """
        Initialize enhanced streamer

        Args:
            preferred_provider: Preferred provider name
            config_path: Path to provider configuration
        """
        self.provider_factory = ProviderFactory(config_path)
        self.preferred_provider = preferred_provider
        self.current_provider: Optional[BaseProvider] = None
        self.data_handler = DataHandler()
        self.redis_cache = get_redis_cache()
        self.prediction_service = HorizonPredictionService()
        ml_settings = get_settings().ml
        self.training_scheduler = BackgroundTrainingScheduler(
            min_new_records=ml_settings.min_samples_for_retrain,
            retrain_interval_hours=ml_settings.retrain_interval_hours,
            check_interval_seconds=ml_settings.retrain_check_interval,
            model_name=ml_settings.default_model,
        )
        self._scheduler_task: Optional[asyncio.Task] = None
        self._lifecycle_task: Optional[asyncio.Task] = None
        self.heartbeat = HeartbeatService()
        self.notifications = NotificationService()
        self.trust = TrustService()
        self._last_prediction_attempt = None

        self.is_running = False
        self.use_websocket = True
        self.current_symbol = 'XAU'

        # Statistics
        self.start_time = None
        self.tick_count = 0
        self.error_count = 0
        self.last_tick_time = None
        self.provider_switches = 0

        logger.info("Enhanced Gold Streamer initialized")

    @staticmethod
    def _record_input_suppression(session, response, reason):
        code = "FUTURE_LIVE_TIMESTAMP" if "future" in reason.lower() else (
            "STALE_CANDLE_CONTEXT" if "candle" in reason.lower() else
            "STALE_LIVE_PRICE" if "stale" in reason.lower() else
            "MARKET_UNAVAILABLE" if "market is closed" in reason.lower() else
            "MISSING_CANDLES" if "missing" in reason.lower() else "INTERNAL_ERROR"
        )
        now = datetime.now(timezone.utc)
        for horizon in get_settings().streaming.prediction_horizons.split(","):
            if not horizon.strip(): continue
            session.add(PredictionDecision(
                decision_at=now, symbol="XAUUSD", provider=response.provider_name,
                horizon_minutes=int(horizon), model_name=None, model_version=None,
                reference_price=response.price_usd, acceptance_status="SUPPRESSED",
                acceptance_reason_code=code, acceptance_reason_detail=reason,
                trust_status_at_decision="DISABLED", data_fresh=False,
                technical_context={"raw_provider_timestamp": (response.metadata or {}).get("rawTimestamp")},
            ))

    async def start(self, symbol: str = 'XAU', mode: str = 'auto'):
        """
        Start streaming with provider failover

        Args:
            symbol: Trading symbol
            mode: 'auto' (auto-detect), 'websocket', or 'polling'
        """
        self.is_running = True
        self.start_time = datetime.now(timezone.utc)
        self.current_symbol = symbol

        logger.info(f"Starting Enhanced Streamer for {symbol} in {mode} mode")

        # Get provider with failover
        self.current_provider = await self.provider_factory.get_provider_with_fallback(
            preferred_provider=self.preferred_provider
        )

        if not self.current_provider:
            logger.error("❌ No providers available - cannot start streaming")
            return

        logger.info(f"✓ Using provider: {self.current_provider.name}")

        if self._scheduler_task is None or self._scheduler_task.done():
            self._scheduler_task = asyncio.create_task(self.training_scheduler.run())
        if self._lifecycle_task is None or self._lifecycle_task.done():
            self._lifecycle_task = asyncio.create_task(self._lifecycle_loop())

        # Determine streaming mode
        if mode == 'auto':
            self.use_websocket = self.current_provider.supports_streaming
        elif mode == 'websocket':
            self.use_websocket = True
        else:
            self.use_websocket = False

        # Start streaming
        try:
            if self.use_websocket and self.current_provider.supports_streaming:
                logger.info("🔄 Starting WebSocket stream...")
                await self._stream_websocket(symbol)
            else:
                logger.info("🔄 Starting polling mode...")
                await self._stream_polling(symbol)
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            self.error_count += 1

    async def _stream_websocket(self, symbol: str):
        """Stream prices using WebSocket"""
        await self.current_provider.stream_prices(
            symbol=symbol,
            on_price=self._handle_tick,
            on_error=self._handle_error
        )

    async def _stream_polling(self, symbol: str):
        """Stream prices using polling"""
        polling_interval = self.current_provider.config.get('polling_interval', 10)

        logger.info(f"Polling every {polling_interval} seconds")

        while self.is_running:
            try:
                start_time = datetime.now()

                # Get quote
                quote = await self.current_provider.get_quote(symbol)

                if quote:
                    await self._handle_tick(quote)

                    # Track response time
                    response_time = (datetime.now() - start_time).total_seconds() * 1000

                    # Update provider status
                    session = get_session()
                    try:
                        update_provider_status(
                            session,
                            self.current_provider.name,
                            is_success=True,
                            response_time=response_time
                        )
                        session.commit()
                    finally:
                        session.close()
                else:
                    logger.warning("No quote received")

                await asyncio.sleep(polling_interval)

            except Exception as e:
                logger.error(f"Polling error: {e}")
                await self._handle_error(e)
                await asyncio.sleep(polling_interval * 2)  # Back off on error

    async def _handle_tick(self, response: ProviderResponse):
        """
        Handle incoming price tick

        Args:
            response: ProviderResponse object
        """
        try:
            self.tick_count += 1
            self.last_tick_time = datetime.now(timezone.utc)

            # Validate data
            if not self.data_handler.validate_tick(response.to_dict()):
                logger.warning("❌ Invalid tick data")
                return

            # Save to database
            session = get_session()
            try:
                price_record = save_unique_price_from_response(session, response)
                session.commit()

                if price_record is None:
                    logger.debug("Skipped duplicate cached price tick")
                    return

                metadata = response.metadata or {}
                logger.info("Persisted provider timestamp evidence: {}", {
                    "provider": response.provider_name,
                    "raw_timestamp_field": metadata.get("rawTimestampField"),
                    "raw_timestamp_value": metadata.get("rawTimestamp"),
                    "raw_timestamp_type": type(metadata.get("rawTimestamp")).__name__,
                    "parsed_timezone": str(response.timestamp.tzinfo),
                    "parsed_provider_timestamp_utc": response.timestamp.astimezone(timezone.utc).isoformat(),
                    "server_utc_now": datetime.now(timezone.utc).isoformat(),
                    "database_created_at": price_record.created_at.isoformat() if price_record.created_at else None,
                    "database_ingested_at": price_record.ingested_at.isoformat() if price_record.ingested_at else None,
                    "difference_seconds": round((response.timestamp.astimezone(timezone.utc)-datetime.now(timezone.utc)).total_seconds(), 3),
                    "request_started_at": metadata.get("requestStartedAt"),
                    "request_completed_at": metadata.get("requestCompletedAt"),
                })

                logger.info(
                    f"💰 {response.symbol}: ${response.price_usd:.2f} "
                    f"[{response.provider_name}] "
                    f"(Tick #{self.tick_count})"
                )

                now = datetime.now(timezone.utc)
                interval = get_settings().streaming.prediction_interval_seconds
                generated = []
                if self._last_prediction_attempt is None or (now-self._last_prediction_attempt).total_seconds() >= interval:
                    self._last_prediction_attempt = now
                    generated = self.prediction_service.generate(session)
                    if generated:
                        manifest = ModelBundleManager().load_manifest()
                        trust = self.trust.refresh(session, manifest)
                        self.notifications.enqueue_forecasts(session, generated, trust)
                        for prediction in generated:
                            state = trust[prediction.horizon_minutes]
                            state.last_prediction_at = prediction.prediction_created_at
                            state.next_target_at = prediction.target_at
                        session.commit()
                health_values = {"last_live_quote_at": response.timestamp}
                if generated:
                    health_values.update(last_prediction_at=generated[0].prediction_created_at, last_error=None)
                elif self.prediction_service.last_unavailable_reason:
                    health_values.update(status="DEGRADED", last_error=self.prediction_service.last_unavailable_reason)
                    self._record_input_suppression(session, response, self.prediction_service.last_unavailable_reason)
                    session.commit()
                self.heartbeat.update(session, **health_values)
                logger.debug(f"Prediction lifecycle: generated={len(generated)}")
            except Exception as e:
                logger.error(f"Database error: {e}")
                session.rollback()
                if isinstance(e, ValueError):
                    self._record_input_suppression(session, response, str(e))
                    session.commit()
            finally:
                session.close()

            # Cache in Redis
            if self.redis_cache and self.redis_cache.is_available():
                try:
                    self.redis_cache.set_latest_tick(response.symbol, response.to_dict())
                    self.redis_cache.add_to_buffer(response.symbol, response.to_dict())
                except Exception as e:
                    logger.debug(f"Redis cache error: {e}")

        except Exception as e:
            logger.error(f"Error handling tick: {e}")
            self.error_count += 1

    async def _handle_error(self, error: Exception):
        """
        Handle streaming error with provider failover

        Args:
            error: Exception that occurred
        """
        logger.error(f"❌ Provider error: {error}")
        self.error_count += 1

        # Update provider status
        session = get_session()
        try:
            update_provider_status(
                session,
                self.current_provider.name if self.current_provider else 'unknown',
                is_success=False,
                error_message=str(error)
            )
            session.commit()
        finally:
            session.close()

        if self.error_count >= 3:
            logger.warning("🔄 Multiple errors detected, attempting provider failover...")
            await self._failover_provider()

    async def _lifecycle_loop(self):
        """Evaluation, delivery and health continue independently of quotes/UI."""
        settings = get_settings().streaming
        while self.is_running:
            session = get_session()
            try:
                now = datetime.now(timezone.utc)
                due_ids = [row[0] for row in session.query(HorizonPrediction.id).filter(
                    HorizonPrediction.status == "PENDING", HorizonPrediction.target_at <= now,
                ).all()]
                changed = self.prediction_service.evaluate_due(session, now=now)
                evaluated = session.query(HorizonPrediction).filter(
                    HorizonPrediction.id.in_(due_ids), HorizonPrediction.status == "EVALUATED",
                ).all() if due_ids else []
                self.notifications.enqueue_outcomes(session, evaluated)
                try:
                    manifest = ModelBundleManager().load_manifest()
                    self.trust.refresh(session, manifest)
                except (FileNotFoundError, ValueError):
                    pass
                self.notifications.deliver_due(session, now)
                latest_training = session.query(RetrainingRun.completed_at).filter(
                    RetrainingRun.status.in_(["PROMOTED", "REJECTED", "FAILED"])
                ).order_by(RetrainingRun.completed_at.desc()).limit(1).scalar()
                health_values = {"status": "RUNNING"}
                if changed:
                    health_values["last_evaluation_at"] = now
                if latest_training:
                    health_values["last_training_at"] = latest_training
                self.heartbeat.update(session, **health_values)
            except Exception as exc:
                session.rollback()
                logger.exception(f"Background lifecycle iteration failed: {exc}")
                try:
                    self.heartbeat.update(session, status="DEGRADED", last_error=str(exc)[:1000])
                except Exception:
                    session.rollback()
            finally:
                session.close()
            await asyncio.sleep(max(1, min(settings.prediction_evaluation_interval_seconds, settings.worker_heartbeat_seconds)))

    async def _failover_provider(self):
        """Failover to another provider"""
        logger.info("Attempting provider failover...")

        # Disconnect current provider
        if self.current_provider:
            try:
                await self.current_provider.disconnect()
            except:
                pass

        # Get new provider (excluding current one)
        new_provider = await self.provider_factory.get_provider_with_fallback(
            preferred_provider=None  # Let factory choose
        )

        if new_provider and new_provider.name != (self.current_provider.name if self.current_provider else None):
            self.current_provider = new_provider
            self.provider_switches += 1
            self.error_count = 0

            logger.info(f"✅ Switched to provider: {new_provider.name}")

            # Restart streaming with new provider
            await self.start(self.current_symbol)
        else:
            logger.error("❌ Failover failed - no alternative providers available")

    async def switch_provider(self, provider_name: str):
        """
        Manually switch to a different provider

        Args:
            provider_name: Name of provider to switch to
        """
        logger.info(f"Manually switching to provider: {provider_name}")

        # Stop current streaming
        was_running = self.is_running
        self.is_running = False

        if self._lifecycle_task and self._lifecycle_task is not asyncio.current_task():
            await self._lifecycle_task

        await self.training_scheduler.stop()
        if self._scheduler_task:
            await self._scheduler_task

        # Disconnect current provider
        if self.current_provider:
            await self.current_provider.disconnect()

        # Get new provider
        new_provider = await self.provider_factory.get_provider(provider_name, auto_connect=True)

        if new_provider:
            self.current_provider = new_provider
            self.provider_switches += 1
            logger.info(f"✅ Switched to {provider_name}")

            # Resume streaming if was running
            if was_running:
                await self.start(self.current_symbol)
        else:
            logger.error(f"❌ Failed to switch to {provider_name}")

    async def stop(self):
        """Stop streaming gracefully"""
        logger.info("Stopping streamer...")
        self.is_running = False

        await self.training_scheduler.stop()
        if self._scheduler_task and self._scheduler_task is not asyncio.current_task():
            await self._scheduler_task
        if self._lifecycle_task and self._lifecycle_task is not asyncio.current_task():
            await self._lifecycle_task

        # Disconnect provider
        if self.current_provider:
            await self.current_provider.disconnect()

        # Disconnect all factory providers
        await self.provider_factory.disconnect_all()

        # Print statistics
        self._print_stats()

        logger.info("✓ Streamer stopped")

    def _print_stats(self):
        """Print streaming statistics"""
        if self.start_time:
            runtime = (datetime.now(timezone.utc) - self.start_time).total_seconds()

            logger.info("="*60)
            logger.info("STREAMING STATISTICS")
            logger.info("="*60)
            logger.info(f"Runtime: {runtime:.1f}s")
            logger.info(f"Ticks received: {self.tick_count}")
            logger.info(f"Errors: {self.error_count}")
            logger.info(f"Provider switches: {self.provider_switches}")
            if self.current_provider:
                logger.info(f"Final provider: {self.current_provider.name}")
            logger.info("="*60)

    def get_stats(self):
        """Get current statistics"""
        runtime = (datetime.now(timezone.utc) - self.start_time).total_seconds() if self.start_time else 0

        return {
            'is_running': self.is_running,
            'runtime_seconds': runtime,
            'tick_count': self.tick_count,
            'error_count': self.error_count,
            'provider_switches': self.provider_switches,
            'current_provider': self.current_provider.name if self.current_provider else None,
            'ticks_per_minute': (self.tick_count / runtime * 60) if runtime > 0 else 0,
            'last_tick': self.last_tick_time.isoformat() if self.last_tick_time else None
        }


# Signal handlers for graceful shutdown
streamer_instance = None

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global streamer_instance
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    if streamer_instance:
        asyncio.create_task(streamer_instance.stop())


async def main():
    """Main entry point for standalone execution"""
    global streamer_instance

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create streamer
    streamer_instance = EnhancedGoldStreamer()

    try:
        # Start streaming
        await streamer_instance.start(symbol='XAU', mode='auto')
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await streamer_instance.stop()


if __name__ == "__main__":
    run_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".run")
    os.makedirs(run_dir, exist_ok=True)
    # Opening with a+ avoids truncating the active owner's PID when a second
    # process probes the lock and is rejected.
    lock_stream = open(os.path.join(run_dir, "background-worker.lock"), "a+")
    try:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error("Another background worker instance is already active")
        raise SystemExit(2)
    lock_stream.seek(0)
    lock_stream.truncate()
    lock_stream.write(f"{os.getpid()}\n")
    lock_stream.flush()
    asyncio.run(main())
