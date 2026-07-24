@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
set "WORK=%ROOT%_build_workspace"
set "OUTPUT=%ROOT%KageLink-v3.4.1.apk"

echo ================================================================
echo KAGELINK 3.4.1 - CONTROLES CONFIGURAVEIS E STATS
echo ================================================================
echo.

where flutter >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Flutter nao foi encontrado no PATH.
    echo [ERROR] Flutter was not found in PATH.
    pause
    exit /b 1
)

echo [0/7] Validando arquivos de localizacao...
if not exist "%ROOT%lib\l10n\app_en.arb" (
    echo [ERRO] Arquivo fallback app_en.arb nao encontrado.
    pause
    exit /b 1
)
if not exist "%ROOT%lib\l10n\app_en_US.arb" (
    echo [ERRO] Arquivo regional app_en_US.arb nao encontrado.
    pause
    exit /b 1
)
if not exist "%ROOT%lib\l10n\app_pt.arb" (
    echo [ERRO] Arquivo fallback app_pt.arb nao encontrado.
    pause
    exit /b 1
)
if not exist "%ROOT%lib\l10n\app_pt_BR.arb" (
    echo [ERRO] Arquivo regional app_pt_BR.arb nao encontrado.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$files=@('%ROOT%lib\l10n\app_en.arb','%ROOT%lib\l10n\app_en_US.arb','%ROOT%lib\l10n\app_pt.arb','%ROOT%lib\l10n\app_pt_BR.arb');" ^
  "$json=$files | ForEach-Object { Get-Content -LiteralPath $_ -Raw | ConvertFrom-Json };" ^
  "$base=@($json[0].PSObject.Properties.Name | Where-Object { -not $_.StartsWith('@') } | Sort-Object);" ^
  "foreach($item in $json){$keys=@($item.PSObject.Properties.Name | Where-Object { -not $_.StartsWith('@') } | Sort-Object); if(Compare-Object $base $keys){throw 'Os arquivos ARB possuem chaves de traducao diferentes.'}}"
if errorlevel 1 (
    echo [ERRO] Os arquivos de idioma nao passaram na validacao.
    pause
    exit /b 1
)

if exist "%WORK%" rmdir /s /q "%WORK%"

echo [1/7] Criando base Android compativel...
call flutter create --platforms=android --org com.kagelink --project-name kagelink "%WORK%"
if errorlevel 1 goto :error

echo [2/7] Copiando aplicativo, idiomas e identidade visual...
xcopy "%ROOT%lib" "%WORK%\lib" /E /I /Y >nul
xcopy "%ROOT%assets" "%WORK%\assets" /E /I /Y >nul
if exist "%WORK%\test" rmdir /s /q "%WORK%\test"
if exist "%ROOT%test" xcopy "%ROOT%test" "%WORK%\test" /E /I /Y >nul
copy /Y "%ROOT%pubspec.yaml" "%WORK%\pubspec.yaml" >nul
copy /Y "%ROOT%analysis_options.yaml" "%WORK%\analysis_options.yaml" >nul
copy /Y "%ROOT%l10n.yaml" "%WORK%\l10n.yaml" >nul

if exist "%ROOT%android_overlay\app\src" (
    xcopy "%ROOT%android_overlay\app\src" "%WORK%\android\app\src" /E /I /Y >nul
)

rem Configuracao conservadora para evitar crash do daemon Kotlin/Gradle.
(
echo org.gradle.jvmargs=-Xmx2048m -Xms512m -XX:MaxMetaspaceSize=512m -XX:-UseParallelGC -Dfile.encoding=UTF-8
echo kotlin.compiler.execution.strategy=in-process
echo org.gradle.daemon=false
echo org.gradle.parallel=false
echo org.gradle.workers.max=2
echo kotlin.incremental=false
echo android.useAndroidX=true
echo android.enableJetifier=true
) > "%WORK%\android\gradle.properties"

pushd "%WORK%"

echo [3/7] Instalando dependencias...
call flutter pub get
if errorlevel 1 (
    popd
    goto :error
)

echo [4/7] Gerando localizacoes pt / pt-BR / en / en-US...
call flutter gen-l10n
if errorlevel 1 (
    popd
    goto :error
)

echo [5/7] Analisando codigo Flutter...
call flutter analyze
if errorlevel 1 (
    echo [ERRO] A analise Flutter encontrou problemas.
    echo Corrija o relatorio acima antes de gerar o APK release.
    popd
    goto :error
)

echo [6/7] Compilando APK release...
set "GRADLE_OPTS=-Dorg.gradle.daemon=false -Dkotlin.compiler.execution.strategy=in-process"
call flutter build apk --release
if errorlevel 1 (
    popd
    goto :error
)

popd

echo [7/7] Copiando resultado...
copy /Y "%WORK%\build\app\outputs\flutter-apk\app-release.apk" "%OUTPUT%" >nul
if errorlevel 1 goto :error

echo.
echo ================================================================
echo APK CRIADO COM SUCESSO / APK BUILT SUCCESSFULLY
echo %OUTPUT%
echo ================================================================
explorer /select,"%OUTPUT%"
pause
exit /b 0

:error
echo.
echo [ERRO / ERROR] Nao foi possivel concluir a compilacao.
echo O diretorio foi mantido para diagnostico:
echo %WORK%
pause
exit /b 1
