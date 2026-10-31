# Input files, units, and GridLAB-D object assignments

## Household demand (excluding water heating)

The placeholder files in `data/input/` have the same structure expected for the
course datasets.  Replace them with the supplied files, then regenerate the
player files with `python3 scripts/generate_profiles.py`.

| House | Input file | Unit | GridLAB-D object | Property | Conversion used |
|---|---|---|---|---|---|
| 1 | `data/input/house1_demand.csv` | kW (nominal real power) | `house_load_1` (`triplex_load`) | `base_power_1`, `base_power_2` | `base_power_leg = (P_kW * 1000 / 2) / 0.95` VA |
| 2 | `data/input/house2_demand.csv` | kW (nominal real power) | `house_load_2` (`triplex_load`) | `base_power_1`, `base_power_2` | same |
| 3 | `data/input/house3_demand.csv` | kW (nominal real power) | `house_load_3` (`triplex_load`) | `base_power_1`, `base_power_2` | same |

The player files written to `data/players/houseN_load.player` contain two
columns: `base_power_1` and `base_power_2` in VA.  The two legs are assumed
balanced.  A common 0.95 lagging power factor is applied through
`power_pf_1/2`, `current_pf_1/2`, and `impedance_pf_1/2`.  The power factor is a
study assumption, not a property inferred from the demand dataset.

## Water draw

| House | Input file | Unit | GridLAB-D object | Property | Conversion used |
|---|---|---|---|---|---|
| 1 | `data/input/house1_water.csv` | gal/min (gpm) | `wh_1` (`waterheater`) | `water_demand` | none; player supplies gpm directly |
| 2 | `data/input/house2_water.csv` | gal/min (gpm) | `wh_2` (`waterheater`) | `water_demand` | none |
| 3 | `data/input/house3_water.csv` | gal/min (gpm) | `wh_3` (`waterheater`) | `water_demand` | none |

The water-draw profile is not an electrical power input.  It drives the
water-heater thermal model, which then determines the electrical element demand.

## Water-heater settings (all three houses)

| Parameter | Value | GridLAB-D property |
|---|---|---|
| Location | indoors | `location INSIDE` |
| Tank setpoint | 120 degF | `tank_setpoint` |
| Tank volume | 50 gal | `tank_volume` |
| Thermostat dead band | 2 degF | `thermostat_deadband` |
| Heating element | 4.5 kW | `heating_element_capacity` |
| Inlet water | 60 degF | `inlet_water_temperature` |
| Tank UA | 3.3 Btu/(h*degF) | `tank_UA` (see note) |
| Initial tank state | 120 degF, full tank | `temperature` |
| Model | one-node | `waterheater_model ONEZNODE` |
| Heat source | electric resistance | `heat_mode ELECTRIC` |

GridLAB-D 5.3 publishes `tank_UA` with the unit string `Btu*h/degF`, but the
water-heater equations use the value as the conventional tank UA in
Btu/(h*degF).  The model therefore sets the numeric value `3.3` and documents
the convention here.

## Service and transformer objects

| Object | Class | Role |
|---|---|---|
| `source_bus` | `node` | 7.2 kV swing source (phase C-N) |
| `xfmr` | `transformer` | shared single-phase center-tapped transformer |
| `secondary_bus` | `triplex_node` | 240/120 V secondary bus |
| `service_drop_1/2/3` | `triplex_line` | 50/75/100 ft service drops |
| `service_meter_1/2/3` | `triplex_meter` | service meters; measure combined household + water-heater demand |
| `house_load_1/2/3` | `triplex_load` | explicit household demand, driven by load players |
| `house_1/2/3` | `house` | thermal host only; HVAC and implicit appliances disabled |
| `wh_1/2/3` | `waterheater` | explicit water-heating load, driven by water-draw players |

## ZIP cases

| Case file | Constant power | Constant current | Constant impedance |
|---|---:|---:|---:|
| `glm/cases/constant_power.glm` | 1.00 | 0.00 | 0.00 |
| `glm/cases/constant_current.glm` | 0.00 | 1.00 | 0.00 |
| `glm/cases/constant_impedance.glm` | 0.00 | 0.00 | 1.00 |
| `glm/cases/mixed.glm` | 0.30 | 0.30 | 0.40 |

All ZIP components use 0.95 lagging power factor.  Water draws, water-heater
settings, initial conditions, and network configuration are identical across
the four cases.

## Transformer candidates

The runner tests 10, 15, 25, and 37.5 kVA single-phase center-tapped
transformers.  The selection criterion is:

- transformer-input apparent power at or below 100% of nameplate for every
  one-minute sample in all four ZIP cases;
- all monitored service leg voltages between 0.95 and 1.05 p.u. on a 120 V
  line-to-neutral base.

## Placeholder data notice

The course datasets were not present in this repository when the skeleton was
created.  `scripts/generate_profiles.py` creates deterministic synthetic
profiles with seed 530 so the model, runners, analysis, and figures can be
exercised.  The metadata is written to `data/profiles_metadata.json`.  Replace
the CSV inputs with the official data and rerun the generator before using any
numerical result in the project report.
