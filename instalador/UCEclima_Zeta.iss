; Instalador de UCEclima Zeta (Inno Setup 6). Un solo archivo: UCEclima_Zeta_Setup.exe
; - Se instala APARTE de Omega (AppId propio): las dos versiones conviven.
; - Instala SIN permisos de administrador en %LOCALAPPDATA%\Programs\UCEclima Zeta (se puede elegir otra carpeta).
; - Desinstalar borra el programa; los proyectos (Documentos\UCEclima_proyectos) NO se borran.
#define AppName "UCEclima Zeta"
#define AppVer "8.0.0-zeta"

[Setup]
AppId={{E0F7EC42-331A-4851-A3FB-D443DBEB98D6}
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
OutputBaseFilename=UCEclima_Zeta_Setup
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
VersionInfoVersion=8.0.0.0
VersionInfoCompany=GICARH · Universidad Central del Ecuador
VersionInfoDescription=UCEclima Zeta · hidrología e hidráulica

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el &Escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\build_dist_zeta\UCEclima\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "LEEME_Zeta.txt"; DestDir: "{app}"; DestName: "LEEME.txt"; Flags: ignoreversion isreadme

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\UCEclima.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\{#AppName} · Mis proyectos"; Filename: "{userdocs}\UCEclima_proyectos"
Name: "{autoprograms}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\UCEclima.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\UCEclima.exe"; Description: "Abrir UCEclima Zeta ahora"; Flags: nowait postinstall skipifsilent

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
                'Ojo: esa configuración la comparten Omega y Zeta. Tus proyectos en Documentos\UCEclima_proyectos NO se borran. Tus credenciales de Earth Engine las gestiona Google y tampoco se tocan.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Cfg, True, True, True);
  end;
end;
