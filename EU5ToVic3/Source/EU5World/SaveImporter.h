#pragma once
#include "BuildingManager/BuildingManager.h"
#include "CountryManager/EU5CountryManager.h"
#include "CultureManager/CultureManager.h"
#include "LocationManager/LocationManager.h"
#include "PopulationManager/PopulationManager.h"
#include "ReligionManager/ReligionManager.h"
#include <filesystem>

namespace EU5
{
enum class MissingBuildingPopPolicy { Reject, SkipP001 };

struct ConversionBuildingSelection
{
	std::map<int, std::shared_ptr<const Building>> included;
	std::map<int, std::shared_ptr<const Building>> skipped;
};

// Shared C++ input model for the personal import stage. It produces no V3 mod.
class SaveImporter
{
  public:
	void load(const std::filesystem::path& source, const std::filesystem::path& decodedOutput = {});
	void parse(std::istream& input);
	[[nodiscard]] std::string report(const std::filesystem::path& installation = {},
		 const std::vector<std::filesystem::path>& modDirectories = {},
		 MissingBuildingPopPolicy policy = MissingBuildingPopPolicy::Reject) const;
	// P001 filters source buildings before downstream aggregation, without mutating the raw import.
	// Other validation errors must still be checked before using this selection for conversion.
	[[nodiscard]] ConversionBuildingSelection selectBuildingsForConversion() const;
	[[nodiscard]] const auto& getPopulationManager() const { return populationManager; }
	[[nodiscard]] const auto& getLocationManager() const { return locationManager; }
	[[nodiscard]] const auto& getCountryManager() const { return countryManager; }
	[[nodiscard]] const auto& getCultureManager() const { return cultureManager; }
	[[nodiscard]] const auto& getReligionManager() const { return religionManager; }
	[[nodiscard]] const auto& getBuildingManager() const { return buildingManager; }
	[[nodiscard]] const auto& getVersion() const { return version; }
  private:
	LocationManager locationManager;
	CountryManager countryManager;
	CultureManager cultureManager;
	BuildingManager buildingManager;
	PopulationManager populationManager;
	ReligionManager religionManager;
	std::filesystem::path sourcePath;
	bool loaded = false;
	bool binary = false;
	std::string version;
	std::string saveDate;
	std::string playerName;
	int player = -1;
	std::map<std::string, std::string> mods;
	std::set<std::string> ignoredSections;
};

int runImportAudit(int argc, const char* argv[]);
}
