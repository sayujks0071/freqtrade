#!/bin/bash
# Freqtrade Backtesting & Optimization Script
# For MomentumVolumeTrend Strategy

cd /Users/mac/freq/ft_userdata

echo "🚀 Starting Freqtrade Strategy Testing Pipeline"
echo "================================================"
echo ""

# ===========================
# 1. BACKTEST (2 Years Data)
# ===========================

echo "📊 Phase 1: Backtesting on 2 years of data..."
echo "Timerange: 2024-01-01 to 2026-01-31"
echo ""

docker compose run --rm freqtrade backtesting \
  --strategy MomentumVolumeTrend \
  --timerange 20240101-20260131 \
  --timeframe 5m \
  --export trades \
  --export-filename user_data/backtest_results/mvt_2year.json

echo ""
echo "✅ Backtest complete! Results saved to backtest_results/mvt_2year.json"
echo ""

# ===========================
# 2. HYPERPARAMETER OPTIMIZATION
# ===========================

echo "🔧 Phase 2: Hyperparameter Optimization..."
echo "This will take 30-60 minutes..."
echo ""

docker compose run --rm freqtrade hyperopt \
  --strategy MomentumVolumeTrend \
  --hyperopt-loss SharpeHyperOptLoss \
  --timerange 20240101-20251031 \
  --timeframe 5m \
  --epochs 300 \
  --spaces buy \
  --export-filename hyperopt_results/mvt_optimized.json

echo ""
echo "✅ Optimization complete! Best parameters saved."
echo ""

# ===========================
# 3. VALIDATION (Out-of-Sample)
# ===========================

echo "✅ Phase 3: Out-of-sample validation..."
echo "Testing on Nov 2025 - Jan 2026 (unseen data)"
echo ""

docker compose run --rm freqtrade backtesting \
  --strategy MomentumVolumeTrend \
  --timerange 20251101-20260131 \
  --timeframe 5m \
  --export trades \
  --export-filename backtest_results/mvt_validation.json

echo ""
echo "✅ Validation complete!"
echo ""

# ===========================
# 4. ANALYSIS
# ===========================

echo "📈 Phase 4: Generating performance analysis..."
echo ""

docker compose run --rm freqtrade backtesting-analysis \
  --export-filename backtest_results/mvt_2year.json \
  --analysis-groups 0 1 2

echo ""
echo "================================================"
echo "🏆 Testing Pipeline Complete!"
echo ""
echo "Next Steps:"
echo "1. Review results in user_data/backtest_results/"
echo "2. Check Sharpe Ratio (target > 2.0)"
echo "3. Verify Max Drawdown (target < 15%)"
echo "4. If metrics good → Deploy to dry-run"
echo "5. Monitor for 1 week → Go live"
echo ""
