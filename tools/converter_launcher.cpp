#define UNICODE
#define _UNICODE
#include <windows.h>
#include <filesystem>
#include <string>

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    wchar_t path[32768];
    GetModuleFileNameW(nullptr, path, 32768);
    const auto root = std::filesystem::path(path).parent_path();
    const auto python = root / L"runtime/python.exe";
    const auto app = root / L"tools/converter_desktop.py";
    if (!std::filesystem::exists(python) || !std::filesystem::exists(app)) {
        MessageBoxW(nullptr, L"软件文件不完整。请完整解压转换器目录，不要单独移动 EXE。", L"EU5 → Victoria 3", MB_OK | MB_ICONERROR);
        return 1;
    }
    SetEnvironmentVariableW(L"TCL_LIBRARY", (root / L"runtime/tcl/tcl8.6").c_str());
    SetEnvironmentVariableW(L"TK_LIBRARY", (root / L"runtime/tcl/tk8.6").c_str());
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    auto data = root / L"data";
    std::filesystem::create_directories(data);
    SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    HANDLE log = CreateFileW((data / L"startup.log").c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                             &security, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    std::wstring command = L"\"" + python.wstring() + L"\" -X utf8 \"" + app.wstring() + L"\" --workspace \"" + data.wstring() + L"\"";
    STARTUPINFOW startup{}; startup.cb=sizeof(startup); startup.dwFlags=STARTF_USESTDHANDLES;
    startup.hStdOutput=log; startup.hStdError=log; startup.hStdInput=GetStdHandle(STD_INPUT_HANDLE);
    PROCESS_INFORMATION process{};
    const BOOL ok=CreateProcessW(python.c_str(), command.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, root.c_str(), &startup, &process);
    if(log != INVALID_HANDLE_VALUE) CloseHandle(log);
    if (!ok) { MessageBoxW(nullptr, L"无法启动转换器，请查看 data/startup.log。", L"启动失败", MB_OK | MB_ICONERROR); return 2; }
    CloseHandle(process.hThread); CloseHandle(process.hProcess);
    return 0;
}
