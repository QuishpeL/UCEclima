; Instalador de UCEclima Lambda (Inno Setup 6). Un solo archivo: UCEclima_Lambda_Setup.exe
; - Se instala APARTE de Eta, Zeta y Omega (AppId propio): las versiones conviven.
; - Instala SIN permisos de administrador en %LOCALAPPDATA%\Programs\UCEclima Lambda (se puede elegir otra carpeta).
; - Desinstalar borra el programa; los proyectos (Documentos\UCEclima_proyectos) NO se borran.
#define AppName "UCEclima Lambda"
#define AppVer "9.2.0-lambda"

[Setup]
AppId={{D2C41921-EFCC-4C48-86E3-AC2C02E2D8C0}
AppName={#AppName}
AppVersion={#AppVer}
AppVerName={#AppName} {#AppVer}
AppPublisher=Diego Quishpe Landeta · Doctorado en Gestión Sustentable del Agua y Riego (UCE)
AppSupportURL=https://www.uce.edu.ec
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\build_instalador
OutputBaseFilename=UCEclima_Lambda_9.2_Setup
SetupIconFile=..\uceclima\ui\static\UCEclima.ico
UninstallDisplayIcon={app}\UCEclima.exe
UninstallDisplayName={#AppName} {#AppVer}
WizardStyle=modern
WizardImageFile=banner_grande.bmp
WizardSmallImageFile=banner_pequeno.bmp
Compression=lzma2/ultra64
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion=9.2.0.0
VersionInfoCompany=Doctorado en Gestión Sustentable del Agua y Riego · Universidad Central del Ecuador
VersionInfoDescription=UCEclima Lambda · hidrología e hidráulica

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el &Escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\build_dist_lambda\UCEclima\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "LEEME_Lambda.txt"; DestDir: "{app}"; DestName: "LEEME.txt"; Flags: ignoreversion isreadme

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\UCEclima.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\{#AppName} · Mis proyectos"; Filename: "{userdocs}\UCEclima_proyectos"
Name: "{autoprograms}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\UCEclima.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\UCEclima.exe"; Description: "Abrir UCEclima Lambda ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Cfg: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Cfg := ExpandConstant('{%USERPROFILE}\.uceclima');
    if DirExists(Cfg) and (not UninstallSilent) then
      if MsgBox('¿Borrar también la configuración de UCEclima (memoria del premódulo, ID de tu proyecto de Google Cloud y clave de la API local)?' + #13#10 + #13#10 +
                'Ojo: esa configuración la comparten Omega, Zeta, Eta y Lambda. Tus proyectos en Documentos\UCEclima_proyectos NO se borran. Tus credenciales de Earth Engine las gestiona Google y tampoco se tocan.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Cfg, True, True, True);
  end;
end;
