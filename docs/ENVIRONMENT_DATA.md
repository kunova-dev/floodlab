# Environmental data register (v0.5e)

Environmental Context is a DRAFT contextual product.  It does not classify a
hazard, calculate exposure or infer impact or causality.

## Piura proof sources

| Source | Provider/version | Native resolution | Reference period | Temporal relationship | Access/licence | Purpose and limitation |
| --- | --- | --- | --- | --- | --- | --- |
| Copernicus DEM GLO-30 | Copernicus DEM GLO-30; locally verified v0.4 subset | 30 m | static terrain representation | `STATIC` | Copernicus public data terms, retained v0.4 receipt | Elevation and derived slope context. It is a DSM and is not HAND or a hydrologically conditioned terrain model. |
| HydroRIVERS | HydroSHEDS HydroRIVERS v1.0; locally verified South America subset | 15 arc-second network | static mapped network | `STATIC` | HydroSHEDS licence; retained v0.4 receipt | Distance to a mapped reach only. It does not establish flow, connectivity, flood source, or HAND. |
| ESA CCI Land Cover | C3S/ESA CCI Land Cover v2.1.1, annual 2017 global map | 300 m | calendar year 2017 annual land-cover class | `EVENT_TIME` | ESA CCI/C3S open scientific use with attribution | The annual 2017 product is selected because it is global, historical and overlaps the Piura event year. Its annual class is not an observation of conditions on the flood date and must never be presented as a flood-state measurement. |

The land-cover provider is only permitted to publish a `VALID` asset after it
has a recorded source URL, checksum, version, spatial subset and retrieval
receipt.  A remote retrieval or schema failure is recorded as
`UNAVAILABLE_PROVIDER` or `RETRIEVAL_FAILURE`; it is never converted to a zero
land-cover result.  Until such a verified subset exists, Piura packages retain
the explicit unavailable state.

The C3S/ESA CCI annual maps provide a globally consistent 300 m record for
1992--2020.  The 2017 C3S/CCI v2.1.1 map is therefore a reasonable limited
historical context layer for this proof, but cannot provide sub-event dynamics,
crop state, rainfall, soil moisture, or a causal explanation.
