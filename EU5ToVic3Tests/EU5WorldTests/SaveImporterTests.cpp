#include "SaveImporter.h"
#include "EU5VersionProbe.h"
#include "gtest/gtest.h"
#include <nlohmann/json.hpp>
#include <sstream>
#include <chrono>
#include <fstream>
using namespace std::string_literals;

TEST(PersonalImport, DecodedOutputNeverOverwritesAnExistingFile)
{
	const auto path = std::filesystem::temp_directory_path() /
		("eu5-decoded-output-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".txt");
	{
		std::ofstream file(path, std::ios::binary);
		file << "preserve this existing file";
	}
	EU5::SaveImporter imported;
	EXPECT_THROW(imported.load(path, path), std::runtime_error);
	std::ifstream file(path, std::ios::binary);
	const std::string actual((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
	EXPECT_EQ("preserve this existing file", actual);
	file.close();
	std::filesystem::remove(path);
}

namespace
{
std::string fixture(const std::string& popReference = "4278392407", const std::string& popExtra = "", const std::string& locationExtra = "")
{
	return "metadata={ version=1.3.11 date=1780.7.4 compatibility={ locations={ roma paris } } } "
		"countries={ tags={ 7=ITA } database={ 7={ definition=GEN country_name=ITA owned_locations={ 1 } primary_culture=2 primary_religion=3 capital=1 } } } "
		"culture_manager={ database={ 2={ name=italian culture_definition=italian } } } "
		"religion_manager={ database={ 3={ name=catholic definition=catholic group=christian } } } "
		"population={ database={ 4278392407={ type=peasants culture=2 religion=3 size=1.23456 } " + popExtra + " } } "
		"locations={ locations={ 1={ owner=7 population={ pops={ " + popReference + " } } } " + locationExtra + " } } "
		"building_manager={ database={ 5={ type=farm location=1 pop=4278392407 } } } played_country={ country=7 }";
}
nlohmann::json audit(const std::string& text)
{
	std::istringstream input(text);
	EU5::SaveImporter imported;
	imported.parse(input);
	return nlohmann::json::parse(imported.report());
}
}

TEST(PersonalImport, PreservesLargePopIDsFixedPointAndCurrentCountryTag)
{
	const auto report = audit(fixture());
	EXPECT_EQ("validated_import", report["status"]);
	EXPECT_EQ("1234.56", report["world_population_persons"]);
	EXPECT_EQ("ITA", report["player"]["tag"]);
	EXPECT_EQ("GEN", report["countries"][0]["definition"]);
}

TEST(PersonalImport, RejectsMissingAndRepeatedPopulationReferences)
{
	EXPECT_EQ("failed_validation", audit(fixture("4278392407 123"))["status"]);
	EXPECT_EQ("failed_validation", audit(fixture("4278392407 4278392407"))["status"]);
	EXPECT_EQ("failed_validation", audit(fixture(""))["status"]);
}

TEST(PersonalImport, CrossChecksCountryOwnership)
{
	EXPECT_EQ("failed_validation", audit(fixture("4278392407", "", "2={ owner=7 }"))["status"]);
}

TEST(PersonalImport, MissingSizeIsExplicitlyReportedAndNoneDoesNotConsumeNextRecord)
{
	auto text = fixture("4278392407 20", "19=none 20={ type=slaves culture=2 religion=3 }");
	const auto report = audit(text);
	EXPECT_EQ("validated_import", report["status"]);
	EXPECT_EQ(1, report["counts"]["dead_pop_slots"]);
	EXPECT_EQ(20, report["warnings"][0]["pop_ids"][0]);
	EXPECT_EQ("1234.56", report["world_population_persons"]);
}

TEST(PersonalImport, RefusesDuplicateOrIncompletePopulations)
{
	EXPECT_THROW(audit(fixture("4278392407", "4278392407={ type=slaves culture=2 religion=3 }")), std::runtime_error);
	EXPECT_THROW(audit(fixture("4278392407", "20={ size=2 }")), std::runtime_error);
	EXPECT_THROW(audit(fixture("4278392407", "20={ type=slaves culture=abc religion=3 }")), std::runtime_error);
}

TEST(PersonalImport, PreservesQuotedModNamesAndVersions)
{
	auto text = fixture();
	text.insert(text.find("compatibility="), "playthrough_playset_info={ latest_mods_used={ \"Mod With Spaces\"=1.2.3 } } ");
	EXPECT_EQ("1.2.3", audit(text)["mods"]["Mod With Spaces"]);
}

TEST(PersonalImport, KeepsFractionalResourceWorkersAndUnsignedUnitReferences)
{
	std::istringstream input("max_raw_material_workers=13.38778 units={ 3909091644 } port={ 3154116770 }");
	EU5::Location loc(1, "roma");
	loc.parseData(input);
	EXPECT_DOUBLE_EQ(13.38778, loc.getMaxRawMaterialWorkers());
	ASSERT_EQ(1, loc.getUnitIDs().size());
	EXPECT_EQ(3909091644ULL, loc.getUnitIDs()[0]);
	EXPECT_EQ(3154116770ULL, loc.getPortIDs()[0]);
}

TEST(PersonalImport, RefusesUnsupportedVersionAndMissingRequiredSection)
{
	auto text = fixture();
	text.replace(text.find("1.3.11"), 6, "1.3.12");
	EXPECT_THROW(audit(text), std::runtime_error);
	EXPECT_THROW(audit("metadata={ version=1.3.11 }"), std::runtime_error);
}

TEST(PersonalImport, DetectsDanglingCultureReligionAndBuildingPop)
{
	auto text = fixture();
	text.replace(text.find("culture=2 religion=3 size="), 19, "culture=8 religion=9");
	EXPECT_EQ("failed_validation", audit(text)["status"]);
	text = fixture();
	text.replace(text.find("pop=4278392407"), 14, "pop=123");
	EXPECT_EQ("failed_validation", audit(text)["status"]);
}

TEST(PersonalImport, P001FiltersBuildingsBeforeAggregationWithoutChangingPeopleOrTerritory)
{
	auto text = fixture();
	const std::string original = "5={ type=farm location=1 pop=4278392407 }";
	text.replace(text.find(original), original.size(),
		"5={ type=farm location=1 pop=4278392407 level=2 } "
		"6={ type=trade_office location=1 pop=123 owner=7 level=5 employed=0.5 } "
		"7={ type=embassy location=1 level=1 }");
	std::istringstream input(text);
	EU5::SaveImporter imported;
	imported.parse(input);
	const auto strict = nlohmann::json::parse(imported.report());
	const auto report = nlohmann::json::parse(imported.report({}, {}, EU5::MissingBuildingPopPolicy::SkipP001));
	EXPECT_EQ("failed_validation", strict["status"]);
	EXPECT_EQ("failed_validation", report["source_validation_status"]);
	EXPECT_EQ("validated_import_with_skips", report["status"]);
	EXPECT_TRUE(report["errors"].empty());
	EXPECT_EQ(1, report["checks"]["building_pop_reference_errors"]);
	EXPECT_EQ(0, report["checks"]["unhandled_building_pop_errors"]);
	EXPECT_EQ(3, report["building_selection"]["source_count"]);
	EXPECT_EQ(2, report["building_selection"]["included_count"]);
	EXPECT_EQ(1, report["building_selection"]["skipped_count"]);
	const auto& skipped = report["building_selection"]["skipped"][0];
	EXPECT_EQ(6, skipped["id"]);
	EXPECT_EQ(123, skipped["reference"]);
	EXPECT_EQ(5, skipped["level"]);
	EXPECT_EQ(7, skipped["owner_id"]);
	EXPECT_EQ("roma", skipped["location"]);
	EXPECT_EQ("P001", skipped["policy"]);
	EXPECT_EQ("skipped", skipped["action"]);
	for (const auto* key: {"countries", "locations", "player", "world_population_persons", "counts"})
		EXPECT_EQ(strict[key], report[key]);
	const auto selection = imported.selectBuildingsForConversion();
	EXPECT_TRUE(selection.included.contains(5));
	EXPECT_TRUE(selection.included.contains(7)); // An omitted pop is not a dangling reference.
	EXPECT_FALSE(selection.included.contains(6));
	int selectedLevels = 0;
	for (const auto& [id, building]: selection.included) selectedLevels += building->getLevel();
	EXPECT_EQ(3, selectedLevels); // Skipped levels cannot feed downstream building-based weights.
	EXPECT_EQ(3, imported.getBuildingManager().getBuildings().size());
	EXPECT_EQ(strict, nlohmann::json::parse(imported.report()));
}

TEST(PersonalImport, P001DoesNotHideOtherErrorsOnSkippedBuildingsOrPopulations)
{
	auto text = fixture();
	text.replace(text.find("pop=4278392407"), 14, "pop=123");
	text.replace(text.find("type=farm location=1"), std::string("type=farm location=1").size(), "type=farm location=99");
	text.replace(text.find("culture=2 religion=3 size="), 19, "culture=8 religion=9");
	std::istringstream input(text);
	EU5::SaveImporter imported;
	imported.parse(input);
	const auto report = nlohmann::json::parse(imported.report({}, {}, EU5::MissingBuildingPopPolicy::SkipP001));
	EXPECT_EQ("failed_validation", report["status"]);
	EXPECT_EQ(1, report["building_selection"]["skipped_count"]);
	std::set<std::string> kinds;
	for (const auto& error: report["errors"]) kinds.insert(error["kind"].get<std::string>());
	EXPECT_TRUE(kinds.contains("missing_building_location"));
	EXPECT_TRUE(kinds.contains("missing_pop_culture"));
	EXPECT_TRUE(kinds.contains("missing_pop_religion"));
	EXPECT_FALSE(kinds.contains("missing_building_pop"));
}

TEST(PersonalImport, P001RetainsValidBuildingsAndSkipsReferencesToDeletedPopSlots)
{
	std::istringstream valid(fixture());
	EU5::SaveImporter clean;
	clean.parse(valid);
	const auto cleanReport = nlohmann::json::parse(clean.report({}, {}, EU5::MissingBuildingPopPolicy::SkipP001));
	EXPECT_EQ("validated_import", cleanReport["status"]);
	EXPECT_EQ(0, cleanReport["building_selection"]["skipped_count"]);
	auto text = fixture("4278392407", "123=none");
	text.replace(text.find("pop=4278392407"), 14, "pop=123");
	std::istringstream input(text);
	EU5::SaveImporter imported;
	imported.parse(input);
	const auto selection = imported.selectBuildingsForConversion();
	EXPECT_TRUE(selection.included.empty());
	EXPECT_TRUE(selection.skipped.contains(5));
}

TEST(PersonalPopulation, RejectsNegativeOverpreciseAndOverflowingValues)
{
	EXPECT_EQ(123456, EU5::parsePopulationAmount("1.23456"));
	EXPECT_EQ(1, EU5::parsePopulationAmount("0.00001"));
	for (const auto* text: {"-1", "nan", "1.123456", "1x", "999999999999999999999999999"})
		EXPECT_THROW(EU5::parsePopulationAmount(text), std::runtime_error);
	EXPECT_EQ(4278392407ULL, EU5::parsePopID("4278392407"));
	for (const auto* text: {"-1", "4294967296", "123abc"}) EXPECT_THROW(EU5::parsePopID(text), std::runtime_error);
}

TEST(PersonalVersion, ReadsEmbeddedBranchesAcrossChunkBoundary)
{
	std::istringstream input(std::string(65510, '\0') + "u26q2/release/1.3.11\0"s + "caesar/u26q2/release/1.3.11\0"s);
	const auto version = EU5::versionFromExecutable(input);
	ASSERT_TRUE(version);
	EXPECT_EQ("1.3.11", version->toShortString());
}

TEST(PersonalVersion, RejectsConflictingAndMissingExecutableVersions)
{
	std::istringstream conflicting("u26q2/release/1.3.11 caesar/u26q2/release/1.4.0 ");
	EXPECT_THROW(EU5::versionFromExecutable(conflicting), std::runtime_error);
	std::istringstream missing("FileVersion=1.0");
	EXPECT_FALSE(EU5::versionFromExecutable(missing));
}
