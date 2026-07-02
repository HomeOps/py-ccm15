# Changelog

## [1.1.1](https://github.com/HomeOps/py-ccm15/compare/v1.1.0...v1.1.1) (2026-07-02)


### Bug Fixes

* back-fill partial status dropouts from a per-slot cache ([#63](https://github.com/HomeOps/py-ccm15/issues/63)) ([bad15e4](https://github.com/HomeOps/py-ccm15/commit/bad15e480795feab4299ba40efcd978f0428322f))

## [1.1.0](https://github.com/HomeOps/py-ccm15/compare/v1.0.0...v1.1.0) (2026-06-30)


### Features

* add PEP 561 typing support and pass mypy --strict ([#58](https://github.com/HomeOps/py-ccm15/issues/58)) ([6331c0c](https://github.com/HomeOps/py-ccm15/commit/6331c0c739e8fc9c92b12e1f5f0c945713502bb8))


### Bug Fixes

* use auto fan for active commands with fan off ([#60](https://github.com/HomeOps/py-ccm15/issues/60)) ([774b59c](https://github.com/HomeOps/py-ccm15/commit/774b59c29a22f5f93aca754e42c0099bd46af09b))

## [1.0.0](https://github.com/HomeOps/py-ccm15/compare/v0.6.0...v1.0.0) (2026-06-15)


### ⚠ BREAKING CHANGES

* `password` is now the configured value, not the pre-obfuscated URL value, and write helpers return CCM15ReturnCode instead of bool.

### Features

* obfuscate password and return CCM15ReturnCode from writes ([#55](https://github.com/HomeOps/py-ccm15/issues/55)) ([64b302b](https://github.com/HomeOps/py-ccm15/commit/64b302b98b323ebf98db10c86b018f1afd312246))

## [0.6.0](https://github.com/ocalvo/py-ccm15/compare/v0.5.0...v0.6.0) (2026-06-13)


### Features

* opt-in electric heater (ht) via a TriState desired value ([#44](https://github.com/ocalvo/py-ccm15/issues/44)) ([2912e1b](https://github.com/ocalvo/py-ccm15/commit/2912e1b067f42001d88ca4de053f520a39df2bae))

## [0.5.0](https://github.com/ocalvo/py-ccm15/compare/v0.4.0...v0.5.0) (2026-06-13)


### Features

* opt-in swing control via a TriState desired value ([#43](https://github.com/ocalvo/py-ccm15/issues/43)) ([c95bf12](https://github.com/ocalvo/py-ccm15/commit/c95bf127bc7fc9ef454fad50e793be8875227d49))

## [0.4.0](https://github.com/ocalvo/py-ccm15/compare/v0.3.0...v0.4.0) (2026-06-13)


### Features

* optional password (pwd=) authentication for control commands ([#17](https://github.com/ocalvo/py-ccm15/issues/17)) ([85a635f](https://github.com/ocalvo/py-ccm15/commit/85a635f3358e3b62b60ac877d91a2812b84dac82))

## [0.3.0](https://github.com/ocalvo/py-ccm15/compare/v0.2.4...v0.3.0) (2026-06-13)


### Features

* accept an injected httpx.AsyncClient and manage its lifecycle ([#40](https://github.com/ocalvo/py-ccm15/issues/40)) ([dc145c2](https://github.com/ocalvo/py-ccm15/commit/dc145c29232d7d5b80d107b2e49583c0b319632b))

## [0.2.4](https://github.com/ocalvo/py-ccm15/compare/v0.2.3...v0.2.4) (2026-06-13)


### Bug Fixes

* tolerate transient CCM15 dropouts and report per-device data age ([#34](https://github.com/ocalvo/py-ccm15/issues/34)) ([fe1529c](https://github.com/ocalvo/py-ccm15/commit/fe1529c58964823a084cdeaaf98d6b7607444d7d))

## [0.2.3](https://github.com/ocalvo/py-ccm15/compare/v0.2.2...v0.2.3) (2026-06-13)


### Documentation

* attribute CCM15 protocol to houselabs/home-assistant-mideaccm ([#30](https://github.com/ocalvo/py-ccm15/issues/30)) ([0e788ef](https://github.com/ocalvo/py-ccm15/commit/0e788efa95f53236377ab61fb64fb15c4bbf007b))
* note that this library is consumed by Home Assistant core ([#27](https://github.com/ocalvo/py-ccm15/issues/27)) ([f28101d](https://github.com/ocalvo/py-ccm15/commit/f28101db628611db860d09fb3da602ef50fcbbbf))

## [0.2.2](https://github.com/ocalvo/py-ccm15/compare/v0.2.1...v0.2.2) (2026-06-13)


### Bug Fixes

* handle non-contiguous slots and slaves &gt;= 32 ([#23](https://github.com/ocalvo/py-ccm15/issues/23)) ([d9d7e58](https://github.com/ocalvo/py-ccm15/commit/d9d7e5890d5cf3baf02adc4e28a1e5a3c2fdb80a))

## [0.2.1](https://github.com/ocalvo/py-ccm15/compare/v0.2.0...v0.2.1) (2026-06-13)


### Bug Fixes

* update async_set_state test to current API ([#21](https://github.com/ocalvo/py-ccm15/issues/21)) ([842bd33](https://github.com/ocalvo/py-ccm15/commit/842bd33bad32b53fafad85a567eb0558ce4947de))

## [0.2.0](https://github.com/ocalvo/py-ccm15/compare/v0.1.2...v0.2.0) (2026-06-13)


### Features

* add release-please for automated releases ([#19](https://github.com/ocalvo/py-ccm15/issues/19)) ([7624545](https://github.com/ocalvo/py-ccm15/commit/7624545e23d80ebe58bbe32e09e7ab09f790a874))
