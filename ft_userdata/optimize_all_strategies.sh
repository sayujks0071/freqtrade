#!/bin/bash
# Master Optimization Script
# Backtests and Optimizes ALL strategies

STRATEGIES=("MomentumVolumeTrend" "BollingerRSI" "VolatilityBreakout" "MLPredictor")
TIMEFRAME="5m"
TIMERANGE_BACKTEST="20240101-20260131"
TIMERANGE_HYPEROPT="20240101-20251031"
TIMERANGE_VALIDATE="20251101-20260131"
EPOCHS=30  # Optimized for quicker feedback round

cd /Users/mac/freq/ft_userdata

echo "🚀 Starting Master Optimization Pipeline"
echo "========================================"

for STRAT in "${STRATEGIES[@]}"; do
    echo ""
    echo "⚔️  Processing Strategy: $STRAT"
    echo "----------------------------------------"

    # 1. Backtest
    echo "📊 1. Initial Backtest (2 Years)..."
    docker compose run --rm freqtrade backtesting \
      --config user_data/config_backtest.json \
      --strategy $STRAT \
      --timerange $TIMERANGE_BACKTEST \
      --timeframe $TIMEFRAME \
      --export trades \
      --export-filename user_data/backtest_results/${STRAT}_initial.json

    # 2. Hyperopt
    echo "🔧 2. Hyperparameter Optimization ($EPOCHS Epochs)..."
    docker compose run --rm freqtrade hyperopt \
      --config user_data/config_backtest.json \
      --strategy $STRAT \
      --hyperopt-loss SharpeHyperOptLoss \
      --timerange $TIMERANGE_HYPEROPT \
      --timeframe $TIMEFRAME \
      --epochs $EPOCHS \
      --spaces buy \
      --export-filename user_data/hyperopt_results/${STRAT}_optimized.json

    # 3. Validation
    echo "✅ 3. Out-of-Sample Validation..."
    docker compose run --rm freqtrade backtesting \
      --config user_data/config_backtest.json \
      --strategy $STRAT \
      --timerange $TIMERANGE_VALIDATE \
      --timeframe $TIMEFRAME \
      --export trades \
      --export-filename user_data/backtest_results/${STRAT}_validation.json

    echo "🎉 $STRAT Cycle Complete"
done

echo ""
echo "========================================"
echo "🏆 All Strategies Optimized!"
echo "Review results in user_data/backtest_results/"
