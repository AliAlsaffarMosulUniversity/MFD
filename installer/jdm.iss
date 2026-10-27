; Inno Setup script for Maria Free Download
; Build:  ISCC.exe /DMyAppVersion=1.0.0 installer\jdm.iss
; Wizard order: Welcome -> License agreement (EULA_Terms_of_Use.rtf, must be accepted) -> installation login -> install

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
AppContact=alsfarly2@gmail.com
AppSupportURL=mailto:alsfarly2@gmail.com
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

[InstallDelete]
; remove leftovers of the old name (Jazira Download Manager / JDM)
Type: files; Name: "{app}\JDM.exe"
Type: files; Name: "{autodesktop}\Jazira Download Manager.lnk"
Type: files; Name: "{userstartup}\Jazira Download Manager.lnk"
Type: filesandordirs; Name: "{autoprograms}\Jazira Download Manager"

[Icons]
Name: "{group}\{#MyAppName}";              Filename: "{app}\{#MyAppExe}"
Name: "{group}\Browser Extension Folder";  Filename: "{app}\extension"
Name: "{group}\Uninstall {#MyAppName}";    Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";        Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}";        Filename: "{app}\{#MyAppExe}"; Parameters: "--minimized"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\extension"; Description: "Open the browser extension folder (for Chrome / Edge)"; Flags: postinstall shellexec skipifsilent unchecked

[Code]
{ Installation login: name + password.
  Only salted SHA-256 hashes are stored here, never the real name/password. }
const
  LOGIN_SALT = 'MFD-2026-Mosul';
  USER_HASH  = '09f0e0342c1f0e5baae655b2139edb01d26b2290c7a62ecac42da37d6381b116';
  PASS_HASH  = 'de7e588b77f0afdf2824a878405d8ab9d4baef0ff4eaed5f6d7a360c32c5c060';

var
  LoginPage: TInputQueryWizardPage;
  Verified: Boolean;

{ An update over an existing installation does not ask for the name/password again. }
function IsUpgrade: Boolean;
var
  Key: String;
begin
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6C2B7E51-4A1D-4E8B-9C3F-2D7A51B0E9A4}_is1';
  Result := RegKeyExists(HKLM, Key) or RegKeyExists(HKCU, Key);
  if (not Result) and IsWin64 then
    Result := RegKeyExists(HKLM64, Key) or RegKeyExists(HKLM32, Key);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = LoginPage.ID) and Verified;
end;

procedure InitializeWizard;
begin
  Verified := IsUpgrade;
  LoginPage := CreateInputQueryPage(wpLicense,
    'Installation Login',
    'Enter the name and password to install {#MyAppName}.',
    'Please type the installation name and password you received, then click Next.');
  LoginPage.Add('Name:', False);
  LoginPage.Add('Password:', True);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = LoginPage.ID then
  begin
    if (GetSHA256OfString(LOGIN_SALT + Lowercase(Trim(LoginPage.Values[0]))) = USER_HASH) and
       (GetSHA256OfString(LOGIN_SALT + Trim(LoginPage.Values[1])) = PASS_HASH) then
      Verified := True
    else
    begin
      Verified := False;
      MsgBox('Wrong name or password. Please try again.', mbError, MB_OK);
      LoginPage.Values[1] := '';
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { also blocks silent installs that skip the login page }
  if Verified then
    Result := ''
  else
    Result := 'The installation name and password are required.';
end;
