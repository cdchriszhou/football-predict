from service.calibration_service import calibrate, run_backtest, load_calibrated_params

print("Running calibration (100 iterations)...")
params = calibrate(iterations=100)
bt = params["backtest"]
print("=== Calibration Results ===")
print(f"Result accuracy:      {bt['result_accuracy']}%")
print(f"Score top3 accuracy:  {bt['score_top3_accuracy']}%")
print(f"Brier score:          {bt['brier_score']}")
print(f"Upset detection:      {bt['upset_detection_rate']}%")
print(f"Collusion detection:  {bt['collusion_detection_rate']}%")
print(f"\nKey params:")
print(f"  market_blend={params['market_blend']}, odds_weight={params['weights']['odds']}")
print(f"  score_odds_blend={params['score_odds_blend']}, upset_weight={params['upset_weight']}")
