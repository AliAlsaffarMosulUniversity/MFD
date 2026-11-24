; Inno Setup script for Maria Free Download
; Build:  ISCC.exe /DMyAppVersion=1.0.0 installer\jdm.iss
; Wizard order: Welcome -> License agreement (EULA_Terms_of_Use.rtf, must be accepted) -> install

#ifndef MyAppVersion
  #define MyAppVersion "1.11.1"
#endif
#define MyAppName "Maria Free Download"
#define MyAppExe "MariaFreeDownload.exe"

[Setup]
AppId={{6C2B7E51-4A1D-4E8B-9C3F-2D7A51B0E9A4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Maria Free Download - Mosul, Iraq
AppCopyright=(c) 2026 Maria Free Download. All rights reserved.
VersionInfoCompany=Maria Free Download
VersionInfoCopyright=(c) 2026 Maria Free Download. All rights reserved.
DefaultDirName={autopf}\Maria Free Download
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=MariaFreeDownload-Setup-{#MyAppVersion}
SetupIconFile=..\assets\jdm.ico
WizardSmallImageFile=wizard_small.bmp
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
LicenseFile=EULA_Terms_of_Use.rtf

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup";     Description: "Start Maria Free Download with Windows (in the tray)"; GroupDescription: "Options:"

[Files]
Source: "..\dist\MariaFreeDownload\*";     DestDir: "{app}";           Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\extension\*";    DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "EULA_Terms_of_Use.rtf"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.html"; DestDir: "{app}"; Flags: ignoreversion isreadme

[InstallDelete]
; remove leftovers of the old name (Jazira Download Manager / JDM)
Type: files; Name: "{app}\JDM.exe"
Type: files; Name: "{autodesktop}\Jazira Download Manager.lnk"
Type: files; Name: "{userstartup}\Jazira Download Manager.lnk"
Type: filesandordirs; Name: "{autoprograms}\Jazira Download Manager"

[Icons]
Name: "{group}\{#MyAppName}";              Filename: "{app}\{#MyAppExe}"
Name: "{group}\README";                    Filename: "{app}\README.html"
Name: "{group}\Browser Extension Folder";  Filename: "{app}\extension"
Name: "{group}\Uninstall {#MyAppName}";    Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";        Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}";        Filename: "{app}\{#MyAppExe}"; Parameters: "--minimized"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\extension"; Description: "Open the browser extension folder (for Chrome / Edge)"; Flags: postinstall shellexec skipifsilent unchecked
