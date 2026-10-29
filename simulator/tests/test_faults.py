import random

import pytest

from fermon_simulator.faults import FaultConfig, FaultInjector

CLEAN = FaultConfig(
    temperature_noise_std=0.0,
    pressure_noise_std=0.0,
    abv_noise_std=0.0,
    dropout_rate=0.0,
    spike_rate=0.0,
    disconnect_rate=0.0,
)


def injector(config: FaultConfig, seed: int = 1) -> FaultInjector:
    return FaultInjector(config, random.Random(seed))


def test_zero_rates_return_clean_signal() -> None:
    inj = injector(CLEAN)
    assert inj.begin_tick("tank-1") is True
    assert inj.apply("temperature", 18.25) == 18.25
    assert inj.apply("pressure", 0.4) == 0.4
    assert inj.apply("alcohol", 2.0) == 2.0


def test_same_seed_is_deterministic() -> None:
    config = FaultConfig(dropout_rate=0.2, spike_rate=0.2, disconnect_rate=0.1)

    def run(seed: int) -> list[float | None]:
        inj = injector(config, seed)
        out: list[float | None] = []
        for _ in range(50):
            if inj.begin_tick("t"):
                out.append(inj.apply("temperature", 18.0))
            else:
                out.append(None)
        return out

    assert run(7) == run(7)
    assert run(7) != run(8)


def test_noise_perturbs_value() -> None:
    config = FaultConfig(temperature_noise_std=0.5, dropout_rate=0.0, spike_rate=0.0)
    inj = injector(config)
    values = [inj.apply("temperature", 18.0) for _ in range(200)]
    assert all(v is not None for v in values)
    deviations = [abs(v - 18.0) for v in values if v is not None]
    assert max(deviations) > 0.0
    assert max(deviations) < 5.0


def test_dropout_rate_one_skips_every_reading() -> None:
    inj = injector(FaultConfig(dropout_rate=1.0))
    assert inj.apply("temperature", 18.0) is None


def test_spike_rate_one_goes_out_of_physical_range() -> None:
    inj = injector(FaultConfig(dropout_rate=0.0, spike_rate=1.0))
    assert inj.apply("temperature", 18.0) == 150.0
    pressure = inj.apply("pressure", 0.5)
    alcohol = inj.apply("alcohol", 3.0)
    assert pressure is not None and pressure > 10.0
    assert alcohol is not None and alcohol > 20.0


def test_disconnect_window_silences_device_for_n_ticks() -> None:
    inj = injector(FaultConfig(disconnect_rate=1.0, disconnect_ticks=3))
    assert [inj.begin_tick("tank-1") for _ in range(3)] == [False, False, False]


def test_disconnect_window_ends_and_is_per_device() -> None:
    config = FaultConfig(disconnect_rate=0.0, disconnect_ticks=2)
    inj = injector(config)
    inj._offline_ticks["tank-1"] = 2  # noqa: SLF001
    assert inj.begin_tick("tank-1") is False
    assert inj.begin_tick("tank-2") is True
    assert inj.begin_tick("tank-1") is False
    assert inj.begin_tick("tank-1") is True


@pytest.mark.parametrize("field", ["dropout_rate", "spike_rate", "disconnect_rate"])
def test_rates_must_be_probabilities(field: str) -> None:
    with pytest.raises(ValueError):
        FaultConfig(**{field: 1.5})


def test_disconnect_window_is_exactly_disconnect_ticks_long() -> None:
    cfg = FaultConfig(disconnect_rate=1.0, disconnect_ticks=3)
    inj = FaultInjector(cfg, random.Random(0))
    assert inj.begin_tick("d") is False  # trigger tick is the first silent tick
    # Disable new triggers so the window can end.
    object.__setattr__(inj, "config", FaultConfig(disconnect_rate=0.0, disconnect_ticks=3))
    results = [inj.begin_tick("d") for _ in range(5)]
    assert results == [False, False, True, True, True]
