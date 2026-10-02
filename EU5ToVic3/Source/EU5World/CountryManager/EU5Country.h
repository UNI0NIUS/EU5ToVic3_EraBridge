#ifndef EU5_COUNTRY_H
#define EU5_COUNTRY_H
#include "Parser.h"
#include <optional>
#include <set>
#include <vector>

namespace EU5
{
class Country: commonItems::parser
{
  public:
	Country() = default;
	Country(int theCountryID, std::istream& theStream);

	// Primitives
	void setTag(const std::string& theTag) { tag = theTag; }
	[[nodiscard]] const auto& getID() const { return countryID; }
	[[nodiscard]] const auto& getTag() const { return tag; }
	[[nodiscard]] const auto& getCountryName() const { return countryName; }
	[[nodiscard]] const auto& getAdjective() const { return adjective; }
	[[nodiscard]] const auto& getFlag() const { return flag; }
	[[nodiscard]] const auto& getType() const { return type; }
	[[nodiscard]] const auto& getHistorical() const { return historical; }
	[[nodiscard]] const auto& getCountryType() const { return countryType; }
	[[nodiscard]] const auto& getDefinition() const { return definition; }
	[[nodiscard]] const auto& getOwnedLocations() const { return ownedLocations; }
	[[nodiscard]] const auto& getPrimaryCulture() const { return primaryCulture; }
	[[nodiscard]] const auto& getPrimaryReligion() const { return primaryReligion; }
	[[nodiscard]] const auto& getCapital() const { return capital; }
	[[nodiscard]] const auto& getIgnoredFields() const { return ignoredFields; }

	void setRevolutionaryTarget() { revolutionaryTarget = true; }
	[[nodiscard]] bool isRevolutionaryTarget() const { return revolutionaryTarget; }

  private:
	void registerKeys();

	std::string countryName; // This is the localization key used for map name display. SWE or blagodarnoye.
	std::string adjective;	 // this is apparently an optional field. :/
	std::string flag;			 // should be tag, AGA94?
	std::string type;			 // location, banking?
	std::string historical;	 // presumably same as tag.
	std::string countryType; // "Real"?? Maybe rebels and so on?
	std::string tag;			 // the actual tag
	int countryID = 0;		 // within the savegame.

	bool revolutionaryTarget = false;
	std::string definition;
	std::vector<int> ownedLocations;
	std::optional<int> primaryCulture;
	std::optional<int> primaryReligion;
	std::optional<int> capital;
	std::set<std::string> ignoredFields;
};
} // namespace EU5

#endif // EU5_COUNTRY_H
