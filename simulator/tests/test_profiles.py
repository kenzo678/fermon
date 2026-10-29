import pytest

from fermon_simulator.profiles import PRESETS, FermentationProfile

# Physical limits enforced by the backend.
TEMP_LIMITS = (-20.0, 100.0)
PRESSURE_LIMITS = (0.0, 10.0)
ABV_LIMITS = (0.0, 20.0)


def hours(profile: FermentationProfile, count: int = 400) -> list[float]:
    end = profile.lag_hours + profile.duration_hours
    return [end * 1.5 * i / count for i in range(count + 1)]


@pytest.fixture(params=sorted(PRESETS))
def profile(request: pytest.FixtureRequest) -> FermentationProfile:
    return PRESETS[request.param]


def test_presets_exist() -> None:
    assert {"ale", "lager"} <= set(PRESETS)


def test_alcohol_starts_near_zero(profile: FermentationProfile) -> None:
    assert profile.alcohol(0.0) == pytest.approx(0.0, abs=0.01)


def test_alcohol_reaches_target_at_end(profile: FermentationProfile) -> None:
    end = profile.lag_hours + profile.duration_hours
    assert profile.alcohol(end) == pytest.approx(profile.target_abv, rel=0.01)
    assert profile.alcohol(end * 3) == pytest.approx(profile.target_abv, rel=0.01)


def test_alcohol_is_monotonic(profile: FermentationProfile) -> None:
    values = [profile.alcohol(h) for h in hours(profile)]
    assert all(b >= a for a, b in zip(values, values[1:], strict=False))


def test_pressure_peaks_during_active_phase(profile: FermentationProfile) -> None:
    samples = hours(profile)
    values = [profile.pressure(h) for h in samples]
    peak_hour = samples[values.index(max(values))]
    assert profile.lag_hours < peak_hour < profile.lag_hours + profile.duration_hours
    assert max(values) > 3 * values[0]
    assert profile.pressure(samples[-1]) < max(values) / 3


def test_pressure_bounded(profile: FermentationProfile) -> None:
    values = [profile.pressure(h) for h in hours(profile)]
    assert min(values) >= 0.0
    assert max(values) <= profile.max_pressure


def test_temperature_stays_near_target(profile: FermentationProfile) -> None:
    values = [profile.temperature(h) for h in hours(profile)]
    assert min(values) > profile.target_temperature - 2.0
    assert max(values) < profile.target_temperature + 4.0


def test_values_within_backend_limits(profile: FermentationProfile) -> None:
    for h in hours(profile):
        assert TEMP_LIMITS[0] <= profile.temperature(h) <= TEMP_LIMITS[1]
        assert PRESSURE_LIMITS[0] <= profile.pressure(h) <= PRESSURE_LIMITS[1]
        assert ABV_LIMITS[0] <= profile.alcohol(h) <= ABV_LIMITS[1]


def test_profile_is_deterministic(profile: FermentationProfile) -> None:
    assert profile.temperature(37.5) == profile.temperature(37.5)
    assert profile.pressure(37.5) == profile.pressure(37.5)


def test_negative_elapsed_is_treated_as_start(profile: FermentationProfile) -> None:
    assert profile.alcohol(-5.0) == profile.alcohol(0.0)
    assert profile.pressure(-5.0) == profile.pressure(0.0)
