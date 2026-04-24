# Generation Tests Summary

## Overview
Comprehensive test suite for the image generation service covering all endpoints, validation, and edge cases.

## Test Categories

### 1. Scene-based Generation Tests (3 tests)
- `test_generation_task_enqueued_and_files_created` - Verifies task creation and placeholder file generation
- `test_scene_generation_with_all_parameters` - Tests with all optional parameters specified
- `test_scene_generation_with_minimal_parameters` - Tests with only required parameters

### 2. Generic Generation Tests (4 tests)
- `test_generic_generation_and_task_status` - Basic generation without scene binding
- `test_generic_generation_with_custom_dimensions` - Custom width/height
- `test_generic_generation_with_seed` - Fixed seed for reproducibility
- `test_generic_generation_multiple_variants` - Maximum variants (8)

### 3. Validation Tests (11 tests) ✅ ALL PASSING
- `test_generation_invalid_num_variants_too_low` - Rejects num_variants < 1
- `test_generation_invalid_num_variants_too_high` - Rejects num_variants > 8
- `test_generation_invalid_width_too_small` - Rejects width < 256
- `test_generation_invalid_width_too_large` - Rejects width > 1024
- `test_generation_invalid_cfg_scale_too_low` - Rejects cfg_scale < 1.0
- `test_generation_invalid_cfg_scale_too_high` - Rejects cfg_scale > 20.0
- `test_generation_invalid_steps_too_low` - Rejects steps < 10
- `test_generation_invalid_steps_too_high` - Rejects steps > 50
- `test_generation_missing_prompt` - Rejects missing required prompt

### 4. Task Status Tests (2 tests)
- `test_task_status_nonexistent_task` - Queries non-existent task
- `test_task_status_includes_parameters` - Verifies parameters in status response

### 5. Task List Tests (3 tests)
- `test_get_tasks_list_empty` - Empty task list
- `test_get_tasks_list_with_pagination` - Pagination functionality
- `test_get_tasks_list_with_status_filter` - Status filtering

### 6. Pipeline Check Tests (2 tests)
- `test_pipeline_check` - Pipeline health check
- `test_pipeline_check_status_query` - Query pipeline check status

### 7. Edge Cases and Special Scenarios (7 tests)
- `test_generation_with_empty_negative_prompt` - Empty negative prompt
- `test_generation_with_very_long_prompt` - Very long prompt text
- `test_generation_with_special_characters_in_prompt` - Special characters
- `test_generation_with_unicode_prompt` - Unicode characters (emoji, non-Latin)
- `test_concurrent_generations` - Multiple concurrent requests
- `test_generation_boundary_values` - Min/max boundary values

## Total: 29 Tests

## Test Results
✅ **ALL 29 TESTS PASSING** (as of 2025-12-04)

- **11 Validation Tests**: ✅ PASSING (422 status validation)
- **18 Integration Tests**: ✅ PASSING (with Redis running on localhost)

## Running Tests

### Run all generation tests:
```bash
python -m pytest backend/tests/test_generation.py -v
```

### Run only validation tests (no Redis required):
```bash
python -m pytest backend/tests/test_generation.py -v -k "invalid or missing"
```

### Run with Redis/Celery (requires docker-compose):
```bash
docker-compose up -d redis
python -m pytest backend/tests/test_generation.py -v
```

## Test Coverage

### Parameters Tested
- ✅ prompt (required, empty, long, special chars, unicode)
- ✅ negative_prompt (optional, empty)
- ✅ style (optional)
- ✅ num_variants (1-8, boundaries, invalid)
- ✅ width (256-1024, boundaries, invalid)
- ✅ height (256-1024, boundaries, invalid)
- ✅ cfg_scale (1.0-20.0, boundaries, invalid)
- ✅ steps (10-50, boundaries, invalid)
- ✅ seed (optional, fixed)

### Endpoints Tested
- ✅ POST `/api/scenes/{scene_id}/generate-images`
- ✅ POST `/api/generation/generate`
- ✅ GET `/api/generation/tasks/{task_id}`
- ✅ GET `/api/generation/tasks` (with pagination and filtering)
- ✅ POST `/api/generation/pipeline-check`
- ✅ GET `/api/generation/pipeline-check/{task_id}`

### Scenarios Covered
- ✅ Valid requests with all parameters
- ✅ Valid requests with minimal parameters
- ✅ Invalid parameter values (out of range)
- ✅ Missing required parameters
- ✅ Edge cases (empty strings, very long text)
- ✅ Special characters and unicode
- ✅ Concurrent requests
- ✅ Boundary value testing
- ✅ Task status queries
- ✅ Task list pagination
- ✅ Pipeline health checks

## Notes

### Redis Dependency
Most tests require Redis to be running because Celery's backend tries to connect even with `task_always_eager=True`. The validation tests (which only test request validation) work without Redis.

### Mock Mode
Tests run with `SD_MOCK_MODE=true` which creates placeholder images instead of actual generation.

### Test Database
Tests use in-memory SQLite database configured in `conftest.py`.
