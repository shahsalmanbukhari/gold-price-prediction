import sys
sys.path.insert(0, 'src')
from predict import GoldPricePredictor
print("Starting prediction test...")
try:
    predictor = GoldPricePredictor()
    results = predictor.predict_both_currencies('linear_regression')
    print("PKR:", results.get('PKR'))
    print("USD:", results.get('USD'))
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
