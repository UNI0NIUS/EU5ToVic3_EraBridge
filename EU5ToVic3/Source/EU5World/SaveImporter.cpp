#include "SaveImporter.h"
#include "EU5VersionProbe.h"
#include "ParserHelpers.h"
#include "CommonRegexes.h"
#include "StringUtils.h"
#include "Log.h"
#include "rakaly.h"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>

namespace
{
using Json = nlohmann::ordered_json;

void validateBraces(const std::string& text)
{
	int depth = 0;
	bool quoted = false, escaped = false, comment = false;
	for (const char ch: text)
	{
		if (comment) { if (ch == '\n') comment = false; continue; }
		if (quoted)
		{
			if (escaped) escaped = false;
			else if (ch == '\\') escaped = true;
			else if (ch == '"') quoted = false;
			continue;
		}
		if (ch == '#') comment = true;
		else if (ch == '"') quoted = true;
		else if (ch == '{') ++depth;
		else if (ch == '}' && --depth < 0) throw std::runtime_error("Unbalanced save braces");
	}
	if (depth || quoted) throw std::runtime_error("Truncated save structure");
}

void add(EU5::PopulationAmount& total, const EU5::PopulationAmount amount)
{
	if (amount < 0 || total > std::numeric_limits<EU5::PopulationAmount>::max() - amount)
		throw std::runtime_error("Population total overflow");
	total += amount;
}

using Definitions = std::map<std::string, std::string>;
Definitions definitions(const std::vector<std::filesystem::path>& roots, const std::filesystem::path& relative)
{
	Definitions result;
	// Files with the same relative name are replaced by the last supplied mod.
	std::map<std::filesystem::path, std::filesystem::path> files;
	for (const auto& root: roots)
	{
		const auto folder = root / relative;
		if (!std::filesystem::is_directory(folder)) continue;
		for (const auto& file: std::filesystem::recursive_directory_iterator(folder))
			if (file.is_regular_file() && file.path().extension() == ".txt")
				files[std::filesystem::relative(file.path(), folder)] = file.path();
	}
	for (const auto& [relativeFile, file]: files)
	{
		commonItems::parser parser;
		parser.registerRegex(commonItems::catchallRegex, [&](const std::string& key, std::istream& input) {
			result[key] = file.generic_string();
			commonItems::ignoreItem(key, input);
		});
		parser.parseFile(file);
	}
	return result;
}

Json distribution(const std::map<std::string, EU5::PopulationAmount>& data)
{
	Json result = Json::object();
	for (const auto& [key, amount]: data) result[key] = EU5::populationPersons(amount);
	return result;
}
}

void EU5::SaveImporter::load(const std::filesystem::path& source, const std::filesystem::path& decodedOutput)
{
	if (!decodedOutput.empty() && std::filesystem::exists(decodedOutput))
		throw std::runtime_error("Decoded output already exists; refusing to overwrite: " + decodedOutput.string());
	std::ifstream file(source, std::ios::binary | std::ios::ate);
	if (!file || file.tellg() <= 0 || file.tellg() > 2LL * 1024 * 1024 * 1024)
		throw std::runtime_error("Unreadable, empty or oversized save: " + source.string());
	std::string original(static_cast<std::size_t>(file.tellg()), '\0');
	file.seekg(0);
	if (!file.read(original.data(), static_cast<std::streamsize>(original.size())))
		throw std::runtime_error("Incomplete save read");
	std::string decoded;
	{
		const auto save = rakaly::parseEu5(original);
		binary = save.is_binary();
		const auto melt = save.melt();
		if (melt.has_unknown_tokens()) throw std::runtime_error("Unknown EU5 binary tokens: import refused");
		decoded = original; // Verbatim melt intentionally leaves the destination unchanged.
		melt.writeData(decoded);
	}
	original.clear(); original.shrink_to_fit();
	validateBraces(decoded);
	sourcePath = source;
	std::istringstream stream(std::move(decoded));
	parse(stream);
	if (!decodedOutput.empty())
	{
		if (!decodedOutput.parent_path().empty()) std::filesystem::create_directories(decodedOutput.parent_path());
		std::ofstream output(decodedOutput, std::ios::binary | std::ios::out | std::ios::noreplace);
		const auto contents = stream.view();
		output.write(contents.data(), static_cast<std::streamsize>(contents.size()));
		output.close();
		if (!output) throw std::runtime_error("Could not write new decoded save: " + decodedOutput.string());
	}
}

void EU5::SaveImporter::parse(std::istream& input)
{
	if (loaded) throw std::runtime_error("Use a new importer for each save");
	loaded = true;
	locationManager.setStrictValidation(true);
	std::set<std::string> sections;
	auto once = [&](const std::string& key) {
		if (!sections.insert(key).second) throw std::runtime_error("Duplicate save section: " + key);
	};
	commonItems::parser compatibility, playset, metadata, playerParser, root;
	compatibility.registerKeyword("locations", [&](std::istream& stream) {
		int id = 0;
		for (const auto& name: commonItems::getStrings(stream)) locationManager.registerLocation(++id, name);
	});
	compatibility.IgnoreUnregisteredItems();
	playset.registerKeyword("latest_mods_used", [&](std::istream& stream) {
		for (const auto& [name, modVersion]: commonItems::assignments(stream).getAssignments())
			mods.emplace(commonItems::remQuotes(name), commonItems::remQuotes(modVersion));
	});
	playset.IgnoreUnregisteredItems();
	metadata.registerKeyword("version", [&](std::istream& stream) { once("metadata.version"); version = commonItems::getString(stream); });
	metadata.registerKeyword("date", [&](std::istream& stream) { saveDate = commonItems::getString(stream); });
	metadata.registerKeyword("player_country_name", [&](std::istream& stream) { playerName = commonItems::getString(stream); });
	metadata.registerKeyword("compatibility", [&](std::istream& stream) { compatibility.parseStream(stream); });
	metadata.registerKeyword("playthrough_playset_info", [&](std::istream& stream) { playset.parseStream(stream); });
	metadata.IgnoreUnregisteredItems();
	playerParser.registerKeyword("country", [&](std::istream& stream) { once("player.country"); player = readEntityID(stream); });
	playerParser.IgnoreUnregisteredItems();
	root.registerRegex("SAV.*", [](const std::string&, std::istream&) {});
	root.registerKeyword("metadata", [&](std::istream& stream) { once("metadata"); metadata.parseStream(stream); });
	root.registerKeyword("countries", [&](std::istream& stream) { once("countries"); countryManager.loadCountries(stream); });
	root.registerKeyword("locations", [&](std::istream& stream) { once("locations"); locationManager.loadLocations(stream); });
	root.registerKeyword("population", [&](std::istream& stream) { once("population"); populationManager.loadPopulations(stream); });
	root.registerKeyword("culture_manager", [&](std::istream& stream) { once("culture_manager"); cultureManager.loadCultures(stream); });
	root.registerKeyword("religion_manager", [&](std::istream& stream) { once("religion_manager"); religionManager.loadReligions(stream); });
	root.registerKeyword("building_manager", [&](std::istream& stream) { once("building_manager"); buildingManager.loadBuildings(stream); });
	root.registerKeyword("played_country", [&](std::istream& stream) { once("played_country"); playerParser.parseStream(stream); });
	root.IgnoreAndStoreUnregisteredItems(ignoredSections);
	root.parseStream(input);
	for (const auto& key: {"metadata", "countries", "locations", "population", "culture_manager", "religion_manager", "building_manager", "played_country"})
		if (!sections.contains(key)) throw std::runtime_error("Missing required save section: " + std::string(key));
	if (version != "1.3.11") throw std::runtime_error("Personal EU5 importer supports exactly 1.3.11; found " + version);
	if (saveDate.empty() || locationManager.getSeenLocations().empty()) throw std::runtime_error("Missing save date/location index");
}

EU5::ConversionBuildingSelection EU5::SaveImporter::selectBuildingsForConversion() const
{
	ConversionBuildingSelection selection;
	const auto& populations = populationManager.getPopulations();
	for (const auto& [id, building]: buildingManager.getBuildings())
	{
		const auto pop = building->getPopID();
		if (pop && !populations.contains(*pop)) selection.skipped.emplace(id, building);
		else selection.included.emplace(id, building);
	}
	return selection;
}

std::string EU5::SaveImporter::report(const std::filesystem::path& installation, const std::vector<std::filesystem::path>& modDirectories,
	 const MissingBuildingPopPolicy policy) const
{
	Json report, errors = Json::array(), warnings = Json::array();
	const bool applyP001 = policy == MissingBuildingPopPolicy::SkipP001;
	const auto selection = selectBuildingsForConversion();
	Json buildingIssues = Json::array(), skippedBuildings = Json::array();
	auto error = [&](const std::string& kind, const auto& id, const auto& reference) {
		errors.push_back({{"kind", kind}, {"id", id}, {"reference", reference}});
	};
	const auto& countries = countryManager.getCountriesByID();
	const auto& cultures = cultureManager.getCultures();
	const auto& religions = religionManager.getReligions();
	const auto& populations = populationManager.getPopulations();
	const auto& locations = locationManager.getAllLocations();
	std::map<int, const Location*> locationsByID;
	std::map<int, PopulationAmount> totals, locationTotals;
	std::map<int, std::set<int>> owned;
	std::map<int, std::map<std::string, PopulationAmount>> cultureTotals, religionTotals, classTotals;
	std::map<PopID, int> references;
	Json omittedSizes = Json::array();
	PopulationAmount world = 0;
	for (const auto& [id, pop]: populations)
	{
		if (!pop.sizePresent) omittedSizes.push_back(id);
		if (!cultures.contains(pop.culture)) error("missing_pop_culture", id, pop.culture);
		if (!religions.contains(pop.religion)) error("missing_pop_religion", id, pop.religion);
	}
	for (const auto& [name, loc]: locations)
	{
		const auto id = loc->getID(), owner = loc->getOwnerID();
		locationsByID[id] = loc.get();
		if (owner != 0)
		{
			owned[owner].insert(id);
			if (!countries.contains(owner)) error("missing_location_owner", id, owner);
		}
		for (const auto popID: loc->getPopIDs())
		{
			if (!references.emplace(popID, id).second) error("duplicate_pop_location", popID, id);
			const auto it = populations.find(popID);
			if (it == populations.end()) { error("missing_location_pop", id, popID); continue; }
			const auto& pop = it->second;
			add(totals[owner], pop.amount); add(locationTotals[id], pop.amount); add(world, pop.amount);
			add(classTotals[owner][pop.type], pop.amount);
			if (cultures.contains(pop.culture)) add(cultureTotals[owner][cultures.at(pop.culture)->getCultureDefinition()], pop.amount);
			if (religions.contains(pop.religion)) add(religionTotals[owner][religions.at(pop.religion).definition], pop.amount);
		}
	}
	for (const auto& [id, pop]: populations)
		if (!references.contains(id)) error("unassigned_pop", id, pop.amount);
	for (const auto& [id, country]: countries)
	{
		const std::set<int> claimed(country->getOwnedLocations().begin(), country->getOwnedLocations().end());
		if (claimed != owned[id]) error("country_owned_locations_mismatch", id, country->getTag());
		if (claimed.size() != country->getOwnedLocations().size()) error("duplicate_owned_location", id, country->getTag());
		if (!claimed.empty())
		{
			if (!country->getPrimaryCulture() || !cultures.contains(*country->getPrimaryCulture())) error("missing_country_culture", id, country->getTag());
			if (!country->getPrimaryReligion() || !religions.contains(*country->getPrimaryReligion())) error("missing_country_religion", id, country->getTag());
			if (!country->getCapital() || !locationsByID.contains(*country->getCapital())) error("missing_capital_location", id, country->getTag());
		}
	}
	for (const auto& [id, building]: buildingManager.getBuildings())
	{
		if (!locationsByID.contains(building->getLocationID())) error("missing_building_location", id, building->getLocationID());
		if (building->getType().empty()) error("missing_building_type", id, "");
		if (selection.skipped.contains(id))
		{
			Json issue = {{"kind", "missing_building_pop"}, {"id", id}, {"reference", *building->getPopID()},
				 {"building_type", building->getType()}, {"level", building->getLevel()}, {"owner_id", building->getOwnerID()},
				 {"location_id", building->getLocationID()}, {"location", locationsByID.contains(building->getLocationID()) ? locationsByID.at(building->getLocationID())->getName() : ""}};
			buildingIssues.push_back(issue);
			if (applyP001)
			{
				issue["policy"] = "P001";
				issue["action"] = "skipped";
				skippedBuildings.push_back(issue);
				warnings.push_back(issue);
			}
			else errors.push_back(issue);
		}
	}
	if (!countries.contains(player)) error("missing_player_country", player, "");
	if (!omittedSizes.empty()) warnings.push_back({{"kind", "omitted_size_defaults_to_zero"}, {"count", omittedSizes.size()}, {"pop_ids", omittedSizes}});

	Json staticDefinitions;
	if (!installation.empty())
	{
		const auto installed = installedVersion(installation / "game");
		if (!installed || installed->toShortString() != version) throw std::runtime_error("EU5 installed/save version mismatch or unknown installation version");
		report["installation_version"] = installed->toShortString();
		std::vector<std::filesystem::path> roots{installation / "game"};
		std::map<std::string, std::string> suppliedMods;
		for (const auto& directory: modDirectories)
		{
			std::ifstream file(directory / ".metadata/metadata.json");
			if (!file) throw std::runtime_error("Missing mod metadata: " + directory.string());
			const auto metadata = Json::parse(file);
			const auto name = metadata.at("name").get<std::string>();
			if (!suppliedMods.emplace(name, metadata.at("version").get<std::string>()).second) throw std::runtime_error("Duplicate supplied mod: " + name);
			roots.push_back(directory);
		}
		if (mods != suppliedMods) throw std::runtime_error("Supplied mod names/versions differ from save latest_mods_used. Save: " + Json(mods).dump() + "; supplied: " + Json(suppliedMods).dump());
		const auto buildings = definitions(roots, "in_game/common/building_types");
		const auto staticCultures = definitions(roots, "in_game/common/cultures");
		const auto staticReligions = definitions(roots, "in_game/common/religions");
		const auto popTypes = definitions(roots, "in_game/common/pop_types");
		const auto staticLocations = definitions(roots, "in_game/map_data/named_locations");
		staticDefinitions = {{"building_types", buildings.size()}, {"cultures", staticCultures.size()}, {"religions", staticReligions.size()}, {"pop_types", popTypes.size()}, {"locations", staticLocations.size()}};
		for (const auto& [id, building]: buildingManager.getBuildings())
			if (!buildings.contains(building->getType())) error("undefined_building_type", id, building->getType());
		for (const auto& [name, loc]: locations)
			if (!staticLocations.contains(name)) error("undefined_location", loc->getID(), name);
		for (const auto& [id, pop]: populations)
			if (!popTypes.contains(pop.type)) error("undefined_pop_type", id, pop.type);
		// Dynamically generated cultures/religions have their own save definitions.
		Json dynamicCultures = Json::array(), dynamicReligions = Json::array();
		for (const auto& [id, culture]: cultures)
			if (!staticCultures.contains(culture->getCultureDefinition())) dynamicCultures.push_back({{"id", id}, {"definition", culture->getCultureDefinition()}});
		for (const auto& [id, religion]: religions)
			if (!staticReligions.contains(religion.definition)) dynamicReligions.push_back({{"id", id}, {"definition", religion.definition}});
		staticDefinitions["save_only_cultures"] = dynamicCultures;
		staticDefinitions["save_only_religions"] = dynamicReligions;
		staticDefinitions["note"] = "Save-only definitions retained for explicit M3 mapping; not silently assigned a vanilla replacement.";
	}
	else report["static_validation"] = "not_requested";

	report["schema"] = "eu5-personal-import-v1";
	report["policies"] = {{"missing_building_pop", applyP001 ? "P001" : "reject"}};
	report["source_building_pop_issues"] = buildingIssues;
	if (applyP001)
		report["building_selection"] = {{"source_count", buildingManager.getBuildings().size()}, {"included_count", selection.included.size()},
			 {"skipped_count", selection.skipped.size()}, {"skipped", skippedBuildings}};
	report["source"] = sourcePath.generic_string();
	report["save_version"] = version;
	report["date"] = saveDate;
	report["binary_input"] = binary;
	report["player"] = {{"id", player}, {"display_name", playerName}, {"population_persons", populationPersons(totals[player])}};
	if (countries.contains(player)) report["player"]["tag"] = countries.at(player)->getTag();
	report["mods"] = mods;
	report["counts"] = {{"countries", countries.size()}, {"metadata_locations", locationManager.getSeenLocations().size()}, {"loaded_locations", locations.size()},
		 {"populations", populations.size()}, {"dead_pop_slots", populationManager.getDeadCount()}, {"cultures", cultures.size()}, {"religions", religions.size()}, {"buildings", buildingManager.getBuildings().size()}};
	report["world_population_persons"] = populationPersons(world);
	report["checks"] = {{"population_and_territory_errors", std::count_if(errors.begin(), errors.end(), [](const auto& entry) { return entry.at("kind") != "missing_building_pop"; })},
		 {"building_pop_reference_errors", buildingIssues.size()},
		 {"unhandled_building_pop_errors", applyP001 ? 0 : buildingIssues.size()}};
	report["population_unit"] = "person; decimal string with two places; saved thousands multiplied by 1000";
	report["countries"] = Json::array();
	std::set<std::string> ignoredCountryFields;
	for (const auto& [id, country]: countries)
	{
		ignoredCountryFields.insert(country->getIgnoredFields().begin(), country->getIgnoredFields().end());
		report["countries"].push_back({{"id", id}, {"tag", country->getTag()}, {"definition", country->getDefinition()}, {"owned_locations", owned[id].size()},
			 {"population_persons", populationPersons(totals[id])}, {"cultures", distribution(cultureTotals[id])}, {"religions", distribution(religionTotals[id])}, {"classes", distribution(classTotals[id])}});
	}
	report["unowned_population_persons"] = populationPersons(totals[0]);
	report["locations"] = Json::array();
	for (const auto& [id, loc]: locationsByID)
		report["locations"].push_back({{"id", id}, {"name", loc->getName()}, {"owner", loc->getOwnerID()}, {"population_persons", populationPersons(locationTotals[id])}});
	report["static_definitions"] = staticDefinitions;
	report["ignored_top_level_sections"] = ignoredSections;
	report["ignored_country_fields"] = ignoredCountryFields;
	report["ignored_population_fields"] = populationManager.getIgnoredFields();
	report["errors"] = errors;
	report["warnings"] = warnings;
	report["source_validation_status"] = errors.empty() && buildingIssues.empty() ? "validated_import" : "failed_validation";
	report["status"] = !errors.empty() ? "failed_validation" : !skippedBuildings.empty() ? "validated_import_with_skips" : "validated_import";
	report["scope"] = "EU5 input audit only; no V3 output or game UI validation";
	return report.dump(2);
}

int EU5::runImportAudit(const int argc, const char* argv[])
{
	std::filesystem::path save, installation, output, decodedOutput;
	std::vector<std::filesystem::path> mods;
	MissingBuildingPopPolicy policy = MissingBuildingPopPolicy::Reject;
	bool policySpecified = false;
	for (int i = 1; i < argc; ++i)
	{
		const std::string option = argv[i];
		if (i + 1 >= argc) throw std::runtime_error("Missing argument after " + option);
		const std::filesystem::path value = argv[++i];
		if (option == "--audit-eu5" && save.empty()) save = value;
		else if (option == "--eu5-dir" && installation.empty()) installation = value;
		else if (option == "--report-dir" && output.empty()) output = value;
		else if (option == "--decoded-save" && decodedOutput.empty()) decodedOutput = value;
		else if (option == "--mod") mods.push_back(value);
		else if (option == "--building-pop-policy" && !policySpecified)
		{
			policySpecified = true;
			if (value == "P001") policy = MissingBuildingPopPolicy::SkipP001;
			else if (value != "strict") throw std::runtime_error("Unknown building population policy; use strict or P001");
		}
		else throw std::runtime_error("Unknown or repeated audit option: " + option);
	}
	if (save.empty() || installation.empty() || output.empty()) throw std::runtime_error("Required: --audit-eu5 SAVE --eu5-dir INSTALL --report-dir NEW_DIRECTORY [--mod MOD_DIRECTORY]");
	if (std::filesystem::exists(output)) throw std::runtime_error("Audit output already exists; choose a new directory");
	if (!std::filesystem::is_regular_file(installation / "game/in_game/map_data/definitions.txt")) throw std::runtime_error("Invalid EU5 installation");
	Log(LogLevel::Info) << "Import audit: reading EU5 save (no Victoria 3 output).";
	SaveImporter imported;
	imported.load(save, decodedOutput);
	Log(LogLevel::Info) << "Import audit: checking object references and installed definitions.";
	const auto report = Json::parse(imported.report(installation, mods, policy));
	if (!output.parent_path().empty()) std::filesystem::create_directories(output.parent_path());
	if (!std::filesystem::create_directory(output)) throw std::runtime_error("Audit output was created by another process");
	std::ofstream file(output / "import_report.json", std::ios::binary);
	file << report.dump(2) << '\n';
	file.close();
	if (!file) throw std::runtime_error("Could not write import report");
	std::cout << Json{{"status", report["status"]}, {"player", report["player"]}, {"counts", report["counts"]}, {"errors", report["errors"].size()}, {"report", (output / "import_report.json").generic_string()}}.dump() << '\n';
	return report["errors"].empty() ? 0 : 2;
}
