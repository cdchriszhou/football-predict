"""
Score Pick Parameter Optimization - Summary and Usage Guide

This module provides comprehensive parameter optimization for the World Cup 2026
score prediction system. All hard-coded thresholds have been migrated to a
centralized configuration system with validation and monitoring capabilities.

## Key Improvements

### 1. Centralized Configuration (score_pick_config.py)
- **60+ configurable parameters** organized into categories:
  - Market thresholds (热门赔率上限、平局赔率上限等)
  - CRS odds gap caps (赔率差距上限)
  - Alignment thresholds (WDL对齐阈值)
  - Upset thresholds (冷门选择阈值)
  - Context thresholds (小组赛情境阈值)
  - Resilience adjustments (弹性调整)

### 2. Parameter Validation
- Automatic bounds checking for all configuration values
- Warning system for out-of-range parameters
- Safe loading with validation (`safe_load_config()`)

### 3. Prediction Tracking (score_prediction_trace.py)
- Decision path recording for each prediction
- Configuration snapshot capture
- Stage-by-stage transformation logging
- Post-analysis tools for parameter usage

### 4. Enhanced Validation (score_pick.py)
- CRS赔率池完整性检查
- 冷门赔率上下限双重检查
- 同向比分赔率差距检查
- 方向覆盖动态阈值配置

## Usage Examples

### Basic Configuration Access
```python
from service.score_pick_config import get_config, heavy_fav_sp_win

# Get all configuration
config = get_config()

# Get specific parameter
threshold = heavy_fav_sp_win()  # Returns 1.55 by default
```

### Custom Configuration Override
```python
from service.score_pick_config import load_config

# Override specific parameters
custom_config = load_config({
    "HEAVY_FAV_SP_WIN": 1.45,  # Lower threshold for heavy favs
    "DRAW_RATE_MIN": 28.0,     # Higher draw rate requirement
})

# Now all predictions will use custom values
```

### Parameter Validation
```python
from service.score_pick_config import validate_config_bounds, safe_load_config

# Check configuration validity
warnings = validate_config_bounds()
if warnings:
    print(f"Configuration warnings: {warnings}")

# Safe loading with automatic validation
config = safe_load_config({"HEAVY_FAV_SP_WIN": 0.95})  # Will trigger warning
```

### Prediction Tracking
```python
from service.score_prediction_trace import PredictionTracker

# Start trace for a match
trace = PredictionTracker.start_trace(match_id="ARG vs BRA")

# Record input parameters
trace.record_input_params({
    "win_rate": 65.0,
    "draw_rate": 25.0,
    "lose_rate": 10.0,
    "expected_a": 2.1,
    "expected_b": 1.2,
})

# Record configuration snapshot
trace.record_config_snapshot(config)

# Record pipeline stages (automatic in decorated functions)
trace.record_stage(
    stage_name="pick_crs_anchored_scores",
    input_scores=["2:1", "1:1"],
    output_scores=["3:0", "2:1"],
    reason="heavy_home_fav_boost",
)

# Record final result
trace.record_final_result(["3:0", "1:1"], "0:0", warnings=[])

# Export trace
print(trace.summary())
trace_json = trace.to_json()
```

### Parameter Usage Analysis
```python
from service.score_prediction_trace import PredictionTracker

# After running many predictions
analysis = PredictionTracker.analyze_parameter_usage()
print(f"Total traces: {analysis['total_traces']}")
print(f"Most used params: {analysis['most_used']}")

# Export all traces for offline analysis
PredictionTracker.export_traces("prediction_traces.json")
```

## Parameter Categories and Defaults

### Market Thresholds
| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| HEAVY_FAV_SP_WIN | 1.55 | [1.10, 2.50] | 热门赔率上限 |
| DRAW_SP_CAP | 3.7 | [2.5, 5.5] | 平局赔率上限 |
| DRAW_RATE_MIN | 26.0 | [15.0, 45.0] | 平局概率下限 |

### Alignment Thresholds
| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| ALIGN_MIN_MARGIN | 6.0 | [2.0, 15.0] | WDL差距触发对齐 |
| ALIGN_MARGIN_STRONG | 8.0 | [4.0, 20.0] | 强对齐阈值 |
| ALIGN_DRAW_PRESERVE_RATE | 20.0 | [10.0, 30.0] | 保留平局门槛 |

### Upset Thresholds
| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| UPSET_DRAW_DEEP_FAV_LIMIT | 55.0 | [25.0, 80.0] | 深盘闷平赔率上限 |
| UPSET_CLUSTER_MIN_WIN_RATE | 52.0 | [40.0, 65.0] | 同向冷门判断阈值 |
| UPSET_MIN_ODD_WARNING | 20.0 | [10.0, 40.0] | 冷门警告阈值 |

### Context Thresholds
| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| RANK_GAP_BLOWOUT | 50.0 | [15.0, 100.0] | 大比分排名差距 |
| RANK_GAP_STALEMATE | 30.0 | [20.0, 50.0] | 闷平排名差距 |
| RANK_HIGH_MINNOW | 75.0 | [50.0, 100.0] | 弱队排名阈值 |

## Testing Results

All **49 test cases** passed successfully after optimization:
- ✅ Sweden blocks same-odds draw promotion
- ✅ Ivory Coast CRS secondary prefers home 1:0
- ✅ Brazil draw promotion when market supports
- ✅ Portugal heavy fav prefers 3:0 over 4:0
- ✅ Germany blowout boost adds 5:0
- ✅ Tunisia/Netherlands away rout not home upset
- ✅ Curacao/Ivory Coast away rout validation

## Next Steps

1. **Parameter Tuning**: Adjust thresholds based on real prediction performance
2. **A/B Testing**: Compare different parameter configurations
3. **Machine Learning**: Train optimal parameter values from historical data
4. **Real-time Monitoring**: Implement dashboard for parameter usage metrics

## Files Modified

- `backend/service/score_pick_config.py` (NEW) - Configuration system
- `backend/service/score_prediction_trace.py` (NEW) - Tracking module
- `backend/service/score_pick.py` - Parameter optimization
- `backend/service/score_context.py` - Resilience optimization

## Backward Compatibility

All changes are backward compatible:
- Default parameters match original hard-coded values
- Test suite validates same behavior
- Old function calls work unchanged
- New configuration features are opt-in
"""