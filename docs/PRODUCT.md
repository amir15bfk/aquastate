# AquaState — Product Context

**Mode:** Operate (a working observatory), with a Read layer for method and sources.
**One sentence:** AquaState tells an analyst where water stress is becoming climate risk, which pressure is driving it, and whether the water system is covered until the next rain.

## Who it serves

Hydrologists, water-agency analysts, resilience officers, climate journalists and NASA Space Apps reviewers who need a defensible country read in under a minute, then need to inspect a dam or a sub-index without leaving the app.

## The one question

**“Are we covered until the next rain?”** at country and dam scale, and **“where is water stress becoming climate risk?”** at world scale.

## Product truth

- The score is deterministic mathematics. No AI agent touches the index path.
- Every number carries formula, inputs, source, confidence and contribution.
- The score is the current-state evidence. “OK until rain” is a separate, forward-looking verdict; it never rewrites the score.
- Data honesty outranks completeness: live, cached, modeled, reference, proxy and unavailable are visibly distinct.
- Country-agnostic: 249 countries scored; the 250-country gazetteer is loaded.
- The dam atlas is a catalogue; only the monitored subset has a live status.
- The world index is a screening aid, not an official water-accounting standard.

## Jobs

1. Glance at the world index and the four pressures.
2. Open a country and read the WCRI pitch and the water runway.
3. Stress a scenario (forecast / dry / rain in two days / demand / horizon) and see when the verdict flips.
4. Open a dam and read the deep DRI arithmetic, buffer bridge, waterfall, sub-indices and analogs.
5. Search the dam atlas and see what is monitored versus inventory-only.
6. Read the method and the source ledger.
7. Leave the page open: the world map refreshes itself on the snapshot cadence.

## Non-goals

- No AI-generated index adjustments.
- No real-time SCADA reservoir telemetry.
- No claim that the dam atlas is a complete global census.
- No operational flood, fire or drought warnings.
- No user accounts or alert delivery in v1.

## The idea

Climate change is usually shown as temperature. The damage arrives through water: a dry winter, a depleted aquifer, a reservoir that cannot reach the next rain, a forest that burns because the soil is dry, a desert that advances, then a storm that runs off hard ground as a flood. AquaState follows that chain.

The signature elements are the **water runway** (days of usable water against the day rain arrives) and the **cascade** (drought → fire → desertification → flood), with an explicit, visible penalty when the cascade is severe.
