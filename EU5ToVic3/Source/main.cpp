#include "ConverterVersion.h"
#include "EU5ToVic3Converter.h"
#include "Log.h"
#include "EU5World/SaveImporter.h"
#include <exception>
#include <fstream>

int main(const int argc, [[maybe_unused]] const char* argv[])
{
	try
	{
		if (argc >= 2 && std::string(argv[1]) == "--audit-eu5")
			return EU5::runImportAudit(argc, argv);
		if (argc >= 2)
			throw std::runtime_error("Unknown option; use --audit-eu5 SAVE --eu5-dir INSTALL --report-dir NEW_DIRECTORY, or no arguments for configuration.txt");
		std::ofstream clearLog("log.txt");
		clearLog.close();

		commonItems::ConverterVersion converterVersion;
		converterVersion.loadVersion("configurables/version.txt");

		Log(LogLevel::Info) << converterVersion;
		convertEU4ToVic3(converterVersion);
		return 0;
	}

	catch (const std::exception& e)
	{
		Log(LogLevel::Error) << e.what();
		return -1;
	}
}
