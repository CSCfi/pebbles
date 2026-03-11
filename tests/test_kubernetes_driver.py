import pytest

from pebbles.drivers.provisioning.kubernetes_driver import calculate_cpu_request_limit_millicore

DEFAULT_COEFF = 0.165  # roughly 14 / 85
MIN_REQUEST = 100  # floor at 0.1 cores => 100m
MIN_LIMIT = 8000


@pytest.mark.parametrize(
    'memory_gib,expected_m',
    [
        # Uses default 0.165 when cluster_config has no key; round to millicores
        (1.0, int(round(1.0 * DEFAULT_COEFF * 1000))),
        (8.0, int(round(8.0 * DEFAULT_COEFF * 1000))),
        (20.0, int(round(20.0 * DEFAULT_COEFF * 1000))),
        (80.0, int(round(80.0 * DEFAULT_COEFF * 1000))),
    ],
)
def test_default_coefficient(memory_gib, expected_m):
    req, lim = calculate_cpu_request_limit_millicore({'memory_gib': memory_gib}, {})
    assert req == expected_m


@pytest.mark.parametrize(
    'memory_gib,expected,case',
    [
        (0.25, 100, 'would be ~41m -> floor to 100m'),
        (0.01, 100, 'floor'),
        (0.0, 100, 'zero to floor'),
        (-2.0, 100, 'negative -> floor applies'),
    ],
)
def test_minimum_floor(memory_gib, expected, case):
    req, lim = calculate_cpu_request_limit_millicore({'memory_gib': memory_gib}, {})
    assert req == expected, case


@pytest.mark.parametrize(
    'coeff,expected,case',
    [
        (0.175, 1400, '8 GiB * 0.175 = 1.4 cores'),
        ('0.25', 2000, 'numeric string is accepted'),
        (0.0, 100, 'zero -> floor'),
        (-1.0, 100, 'negative -> floor'),
    ],
)
def test_custom_coefficients(coeff, expected, case):
    cfg = {'cpuCoresPerGiBRatio': coeff}
    req, lim = calculate_cpu_request_limit_millicore({'memory_gib': 8.0}, cfg)
    assert req == expected, case


@pytest.mark.parametrize(
    'bad_mem',
    ['', 'NaN', 'banana', object()]
)
def test_invalid_memory_gib_resets_to_1_gib(bad_mem):
    # On ValueError, code sets mem_gib to 1.0 and coeff to DEFAULT_COEFF
    req, lim = calculate_cpu_request_limit_millicore({'memory_gib': bad_mem}, {})
    expected_m = int(round(DEFAULT_COEFF * 1000))
    assert req == expected_m


def test_missing_memory_gib_defaults_to_1_gib():
    # provisioning_config has no 'memory_gib' -> uses default 1.0
    req, lim = calculate_cpu_request_limit_millicore({}, dict(cpuCoresPerGiBRatio=1.0))
    expected_m = int(round(1.0 * 1000))
    assert req == expected_m


# positive test cases for request and limit
@pytest.mark.parametrize(
    'memory_gib, cpu_coeff, expected_request, expected_limit, case',
    [
        (1, 1, 1000, MIN_LIMIT, 'limit under floor'),
        (8, 1, 8000, MIN_LIMIT, 'limit at floor'),
        (9, 1, 9000, 9000, 'limit over floor'),
        (9, 0.1, 900, MIN_LIMIT, 'limit under floor, small coeff'),
        (1, 10, 10000, 10000, 'limit over floor, large coeff'),
        (0.5, 0.1, 100, MIN_LIMIT, 'request under floor'),
    ],
)
def test_cpu_limit_format_and_floor(memory_gib, cpu_coeff, expected_request, expected_limit, case):
    req, lim = calculate_cpu_request_limit_millicore({'memory_gib': memory_gib}, {'cpuCoresPerGiBRatio': cpu_coeff})
    assert req == expected_request, case
    assert lim == expected_limit, case


def test_cpu_limit_with_invalid_memory_defaults_to_floor_8():
    # Invalid memory values reset to 1.0 GiB internally, which yields request_cores ~0.165 < 8 => limit '8'
    for bad in ('', 'NaN', 'banana', object()):
        req, lim = calculate_cpu_request_limit_millicore({'memory_gib': bad}, {})
        assert lim == 8000
