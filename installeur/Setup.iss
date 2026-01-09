; Script Inno Setup pour le Système de Pointage Client
; Assurez-vous d'avoir le fichier installeur.bat dans le même dossier

#define MyAppName "Système de Pointage Client"
#define MyAppVersion "1.0"
#define MyAppPublisher "Votre Entreprise"
#define MyAppURL "http://www.votreentreprise.com"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\PointageClient
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=
OutputDir=.
OutputBaseFilename=Installeur_Pointage_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
SetupIconFile=
UninstallDisplayIcon={app}\uninstall.ico

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
; Copier le script d'installation batch
Source: "installeur.bat"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Code]
var
  ServerIPPage: TInputQueryWizardPage;
  ServerIP: String;

procedure InitializeWizard;
begin
  { Créer une page pour demander l'IP du serveur }
  ServerIPPage := CreateInputQueryPage(wpWelcome,
    'Configuration du serveur', 
    'Adresse IP du serveur de pointage',
    'Veuillez entrer l''adresse IP du serveur de pointage (exemple: 192.168.1.100)');
  ServerIPPage.Add('Adresse IP:', False);
  ServerIPPage.Values[0] := '192.168.1.100';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ServerIPPage.ID then
  begin
    ServerIP := ServerIPPage.Values[0];
    if Length(ServerIP) = 0 then
    begin
      MsgBox('Veuillez entrer une adresse IP valide.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  BatchFile: String;
  ModifiedBatch: String;
  Lines: TArrayOfString;
  i: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    { Modifier le fichier batch pour inclure l'IP du serveur }
    BatchFile := ExpandConstant('{tmp}\installeur.bat');
    
    { Lire le fichier batch }
    if LoadStringsFromFile(BatchFile, Lines) then
    begin
      { Modifier la ligne qui demande l'IP }
      for i := 0 to GetArrayLength(Lines) - 1 do
      begin
        if Pos('set /p SERVER_IP=', Lines[i]) > 0 then
        begin
          Lines[i] := 'set SERVER_IP=' + ServerIP;
        end;
        { Supprimer la pause à la fin pour automatiser }
        if Pos('pause', Lines[i]) > 0 then
        begin
          Lines[i] := 'REM pause supprimée pour installation automatique';
        end;
      end;
      
      { Sauvegarder le fichier modifié }
      SaveStringsToFile(BatchFile, Lines, False);
    end;
    
    { Exécuter le script d'installation }
    if MsgBox('L''installation va maintenant configurer le système de pointage automatique.' + #13#10 + 
              'Serveur: ' + ServerIP + #13#10#13#10 + 
              'Continuer ?', mbConfirmation, MB_YESNO) = IDYES then
    begin
      Exec('cmd.exe', '/c "' + BatchFile + '"', '', SW_SHOW, ewWaitUntilTerminated, ResultCode);
      
      if ResultCode = 0 then
      begin
        MsgBox('Installation terminée avec succès !' + #13#10 + 
               'Le système de pointage démarrera automatiquement au prochain redémarrage.', 
               mbInformation, MB_OK);
      end
      else
      begin
        MsgBox('Une erreur s''est produite pendant l''installation.' + #13#10 + 
               'Code d''erreur: ' + IntToStr(ResultCode), 
               mbError, MB_OK);
      end;
    end;
  end;
end;

[Run]
; Ne rien exécuter ici, on le fait dans le code Pascal

[UninstallRun]
; Supprimer la tâche planifiée lors de la désinstallation
Filename: "schtasks"; Parameters: "/delete /tn ""PointageAutomatique"" /f"; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "C:\PointageClient"

[Messages]
WelcomeLabel2=Cet assistant va installer le [name/ver] sur votre ordinateur.%n%nCe logiciel permettra de pointer automatiquement votre arrivée et départ sur le serveur de l'entreprise.
FinishedLabel=L'installation du [name] est terminée.%n%nLe système de pointage démarrera automatiquement au prochain redémarrage de l'ordinateur.