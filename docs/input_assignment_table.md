# Input files, units, and GridLAB-D object assignments

## Selected household demand (excluding water heating)

The supplied pool contains 120 one-minute profiles for 2025-09-01:
`data/input/house_profile_<id>.csv`, with columns `Time` and
`house power (kW)`.  The three-house model uses the first three IDs.  The
selection is recorded in `data/selected_profiles.json` and normalized copies are
written to `data/selected/houseN_demand.csv`.

| House | Supplied file | Unit | GridLAB-D object | Property | Conversion used |
|---|---|---|---|---|---|
| 1 | `data/input/house_profile_1.csv` | kW (nominal real power) | `house_load_1` (`triplex_load`) | `base_power_1`, `base_power_2` | `base_power_leg = (P_kW * 1000 / 2) / 0.95` VA |
| 2 | `data/input/house_profile_2.csv` | kW (nominal real power) | `house_load_2` (`triplex_load`) | `base_power_1`, `base_power_2` | same |
| 3 | `data/input/house_profile_3.csv` | kW (nominal real power) | `house_load_3` (`triplex_load`) | `base_power_1`, `base_power_2` | same |

The player files written to `data/players/houseN_load.player` contain two
columns: `base_power_1` and `base_power_2` in VA.  The two legs are assumed
balanced.  A common 0.95 lagging power factor is applied through
`power_pf_1/2`, `current_pf_1/2`, and `impedance_pf_1/2`.  The power factor is a
study assumption, not a property inferred from the demand dataset.

## Water draw

Water draw comes from the supplied `data/input/water_draw.csv`, a headerless
two-column file (`timestamp`, `water_gpm`).  It has 1445 rows covering 1440
unique one-minute timestamps; the five duplicate timestamps are simultaneous
draw events and are summed.  After summation the profile is 83.979 gal/day, with
65 nonzero draw minutes and a peak of 2.994 gpm.  Normalized copies are written
to `data/selected/houseN_water.csv`.

Only one water-draw profile is supplied for the three-house model.  By default
(`--water-mode shared`) the same profile is applied to each water heater, so each
service sees 83.979 gal/day and the modeled aggregate is 251.937 gal/day.  The
alternative `--water-mode split` treats the file as an aggregate three-house draw
and divides it equally (27.993 gal/day per heater).

| House | Source | Unit | GridLAB-D object | Property | Conversion used |
|---|---|---|---|---|---|
| 1 | `data/input/water_draw.csv` | gal/min (gpm) | `wh_1` (`waterheater`) | `water_demand` | none; player supplies gpm directly |
| 2 | `data/input/water_draw.csv` | gal/min (gpm) | `wh_2` (`waterheater`) | `water_demand` | none |
| 3 | `data/input/water_draw.csv` | gal/min (gpm) | `wh_3` (`waterheater`) | `water_demand` | none |

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

## Data status

The household demand profiles and the water-draw profile are the supplied data.
The simulated day is 2025-09-01, matching both sources.  The main data
assumption is the water-draw assignment: one supplied profile is shared by all
three water heaters in the default mode.  See `results.txt` for the split-mode
sensitivity and the other flagged limitations.
