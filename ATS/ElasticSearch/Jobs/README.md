# Jobs Module

**Type:** Internal scheduled service (no HTTP endpoints)
**Source:** `search-service-1/src/modules/jobs/`

## Overview

The Jobs module runs periodic background sync operations using `@nestjs/schedule` interval decorators. It ensures all ElasticSearch indices stay up-to-date by triggering the Sync service methods at fixed intervals. Each job has a mutex flag to prevent concurrent execution of the same sync.

---

## Scheduled Jobs

### High-Frequency (Real-time-ish)

| Job | Interval | Sync Target | Description |
|-----|----------|-------------|-------------|
| `openForBusiness` | **5 minutes** | `syncDegreeStreamSpecialisation` | Degree-stream-specialisation hierarchy |
| `eventsSchedduler` | **30 seconds** | `syncEventsDegreeStreamSpecialisation` | Events degree-stream-specialisation (near real-time) |

### Standard Frequency (Every 12 Hours)

| Job | Interval | Sync Target |
|-----|----------|-------------|
| `countriesSchedduler` | 12h | `syncCountries` |
| `statesSchedduler` | 12h | `syncStates` |
| `citiesSchedduler` | 12h | `syncCities` |
| `UniversityLISchedduler` | 12h | `fetchUniversitiesLI` |
| `UniversitySCWSchedduler` | 12h | `fetchUniversitiesSCW` |
| `UniversitySSWSchedduler` | 12h | `fetchUniversitiesSSW` |
| `DegreeDepartmentLSSchedduler` | 12h | `fetchDegreeDepartment('LS')` |
| `DegreeDepartmentSSWLSPSchedduler` | 12h | `fetchDegreeDepartment('SSWLSP')` |
| `DegreeDepartmentNOTCMSchedduler` | 12h | `fetchDegreeDepartmentNOTCM` |
| `SpecializationLSSchedduler` | 12h | `fetchSpecialization('LS')` |
| `SpecializationLSPSCWSchedduler` | 12h | `fetchSpecialization('LSP_SCW')` |
| `SpecializationCASSchedduler` | 12h | `fetchSpecializationCAS('CAS')` |
| `SpecializationNOTCASSchedduler` | 12h | `fetchSpecializationCAS('NOT_CAS')` |
| `CollegeNameMasterLSSchedduler` | 12h | `fetchCollegeNameMaster('LS')` |
| `CollegeNameMasterLSPSchedduler` | 12h | `fetchCollegeNameMaster('LSP')` |
| `StudentStateCitySchedduler` | 12h | `syncStudentStateCity` |
| `CityMasterSSWSchedduler` | 12h | `syncCityMaster('SSW')` |
| `CityMasterNOTSSWSchedduler` | 12h | `syncCityMaster('NOT_SSW')` |
| `SkillMasterSchedduler` | 12h | `syncSkillMaster` |
| `FunctionDataSchedduler` | 12h | `syncFunctionData` |
| `SectorDataSchedduler` | 12h | `syncSectorData` |
| `StateWithCountrySchedduler` | 12h | `syncStatesWithCountry` |
| `LocationDetailsSchedduler` | 12h | `syncLocationsWithCityAndCountryAndState` |
| `DegreeDataSchedduler` | 12h | `syncDegreeData` |
| `CampusPreviewListSchedduler` | 12h | `syncCampusPreviewNewList` |
| `CollegeNameCorporateFiltersCASchedduler` | 12h | `syncCollegeNameCorporateFilters('CA')` |
| `CollegeNameCorporateFiltersNOTCASchedduler` | 12h | `syncCollegeNameCorporateFilters('NOT_CA')` |
| `CityRoleCorporateMasterRPSchedduler` | 12h | `syncCityRoleCorporateMaster('RP')` |
| `CityRoleCorporateMasterHSSchedduler` | 12h | `syncCityRoleCorporateMaster('HS')` |
| `CityRoleCorporateMasterNOTRPHSSchedduler` | 12h | `syncCityRoleCorporateMaster('NOT_RP_HS')` |
| `InstituteListSchedduler` | 12h | `syncInstituteList` |
| `InstituteDegreeListSchedduler` | 12h | `syncInstituteDegreeView` |
| `InstituteSpecialisationSchedduler` | 12h | `syncInstitutSpecialisation` |
| `InstitutStreamsSchedduler` | 12h | `syncInstitutStreams` |
| `InstituteLocationsSchedduler` | 12h | `syncInstituteLocations` |
| `CorporateLocationsSchedduler` | 12h | `syncCorporateLocations` |
| `CorporateListSchedduler` | 12h | `syncCorporateList` |
| `StudentCrudSkillSchedduler` | 12h | `syncStudentCrudSkills` |
| `InstituteCrudDegreeDepartmentSchedduler` | 12h | `syncInstituteCrudDegreeDepartment` |
| `CityDetailsSchedduler` | 12h | `syncCitiesWithCountryAndState` |
| `UniversityMasterSchedduler` | 12h | `syncUniversitiesMaster` |
| `InstituteMasterSchedduler` | 12h | `syncInstitutesMaster` |

---

## Key Features

- **Mutex pattern:** Each job has a boolean flag (`isXxxJobRunning`) to prevent overlapping executions
- **Error resilience:** All jobs use `.catch()` to log errors without crashing, then `.finally()` to reset the mutex
- **Two tiers:** Events sync runs every 30s (near real-time); most others run every 12h
- **Full coverage:** Every sync type has a corresponding scheduled job — no manual sync required in steady state
- **Empty date param:** Jobs pass empty string `''` as `query_date`, triggering full syncs each time
