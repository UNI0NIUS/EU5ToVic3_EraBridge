#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <filesystem>
#include <fstream>
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
    const auto data = root / L"data";
    std::filesystem::create_directories(data);
    const auto terms = root / L"licenses/END_USER_TERMS.txt";
    const auto accepted = data / L"third-party-terms-v1.accepted";
    if (std::filesystem::exists(terms) && !std::filesystem::exists(accepted)) {
        while (true) {
            const int choice = MessageBoxW(nullptr,
                L"首次运行需要同意第三方组件使用条款。\n\n"
                L"许可说明：licenses/END_USER_TERMS.txt\n"
                L"微软运行组件按附带的微软条款使用；EraBridge 源码仍采用 MIT 许可。\n\n"
                L"是：同意条款并启动\n否：打开条款阅读\n取消：退出",
                L"EraBridge — 第三方组件条款", MB_YESNOCANCEL | MB_ICONINFORMATION | MB_DEFBUTTON2);
            if (choice == IDCANCEL) return 0;
            if (choice == IDNO) {
                ShellExecuteW(nullptr, L"open", terms.c_str(), nullptr, root.c_str(), SW_SHOWNORMAL);
                continue;
            }
            std::ofstream receipt(accepted);
            receipt << "third-party-terms-v1\n";
            if (!receipt) {
                MessageBoxW(nullptr, L"无法保存许可选择。请将完整软件目录解压到可写入的位置。", L"EraBridge", MB_OK | MB_ICONERROR);
                return 1;
            }
            break;
        }
    }
    SetEnvironmentVariableW(L"TCL_LIBRARY", (root / L"runtime/tcl/tcl8.6").c_str());
    SetEnvironmentVariableW(L"TK_LIBRARY", (root / L"runtime/tcl/tk8.6").c_str());
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
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
