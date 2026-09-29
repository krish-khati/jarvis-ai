# setup_startup.ps1 - Windows login pe JARVIS apne aap chalu (pythonw = koi terminal nahi dikhta)
#
#   Install : powershell -ExecutionPolicy Bypass -File D:\JARVIS\setup_startup.ps1
#   Status  : powershell -ExecutionPolicy Bypass -File D:\JARVIS\setup_startup.ps1 -Status
#   Hatao   : powershell -ExecutionPolicy Bypass -File D:\JARVIS\setup_startup.ps1 -Remove
#
# Startup folder mein sirf ek shortcut banta hai (registry/admin nahi chahiye). Hatana ho to -Remove.
param([switch]$Remove, [switch]$Status)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path $root "venv\Scripts\pythonw.exe"
$main = Join-Path $root "main.py"
$lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "JARVIS.lnk"

if ($Status) {
    if (Test-Path $lnk) { "Startup ON: $lnk" } else { "Startup OFF (shortcut nahi hai)" }
    return
}
if ($Remove) {
    if (Test-Path $lnk) { Remove-Item $lnk -Force; "Startup shortcut hata diya." } else { "Shortcut pehle se nahi tha." }
    return
}
if (-not (Test-Path $pythonw)) { throw "pythonw.exe nahi mila: $pythonw (venv banaya hai?)" }
if (-not (Test-Path $main)) { throw "main.py nahi mila: $main" }

$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = $pythonw
$s.Arguments = "`"$main`""
$s.WorkingDirectory = $root          # .env, models\, memory.json isi folder se padhte hain
$s.WindowStyle = 7                   # minimized (pythonw ka waise bhi koi window nahi)
$s.Description = "J.A.R.V.I.S voice assistant"
$s.Save()
"Startup ON: $lnk"
"Agli baar Windows login pe JARVIS background mein chalega (tray icon dikhega)."
