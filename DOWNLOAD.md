# Download KageLink 3.5.0 / Baixar KageLink 3.5.0

[Português](#português) · [English](#english)

---

## Português

### Download rápido

| Windows | Android |
| --- | --- |
| **[⬇ Baixar instalador para Windows](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Windows-Setup.exe)** | **[⬇ Baixar APK para Android](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Android.apk)** |

Os links acima sempre apontam para a **versão estável mais recente**. O KageLink 3.5.0 inclui o Dojo Trainer no Setup Windows e seus controles remotos no APK.

### Instalação

**Windows**

1. Baixe `KageLink-Windows-Setup.exe`.
2. Feche qualquer KageLink antigo que esteja aberto.
3. Execute o instalador e conclua o assistente.
4. Abra o KageLink pelo atalho ou Menu Iniciar.
5. Na primeira execução, escolha PT-BR ou EN-US e mantenha a porta padrão `8765`, salvo necessidade específica.

O Setup instala automaticamente:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

Os dois helpers do Dojo ficam no mesmo diretório do KageLink e não exigem Python instalado. Não mova ou execute esses arquivos separadamente.

O KageLink cria automaticamente a chave de acesso e a conexão externa segura. A integração LeafOS é opcional.

**Android**

1. Baixe `KageLink-Android.apk` no celular.
2. Abra o APK.
3. Se o Android solicitar permissão para instalar apps dessa origem, autorize a origem que você está usando para abrir o arquivo.
4. Instale e abra o KageLink.
5. No PC, copie o endereço e a chave de acesso exibidos pelo KageLink e use-os para criar a conexão no app.
6. Use a área **Dojo** para iniciar, parar e acompanhar o treino executado no Windows.

O APK é uma interface remota: visão, decisões e comandos de teclado continuam executando somente no PC Agent.

### Verificar o download

A mesma Release inclui `SHA256SUMS.txt`, com os hashes SHA-256 dos dois arquivos oficiais.

**[Ver a Release mais recente](https://github.com/leafoss/KageLink/releases/latest)**

Para instruções completas, consulte o [guia em Português](README.pt-BR.md) e a [documentação do Dojo 3.5](KAGELINK_3_5_DOJO.md).

---

## English

### Quick download

| Windows | Android |
| --- | --- |
| **[⬇ Download Windows installer](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Windows-Setup.exe)** | **[⬇ Download Android APK](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Android.apk)** |

The links above always point to the **latest stable release**. KageLink 3.5.0 includes the Dojo Trainer in the Windows Setup and its remote controls in the APK.

### Installation

**Windows**

1. Download `KageLink-Windows-Setup.exe`.
2. Close any older KageLink instance that is running.
3. Run the installer and complete the wizard.
4. Open KageLink from the shortcut or Start Menu.
5. On first launch, choose PT-BR or EN-US and keep the default port `8765` unless you specifically need another port.

The Setup automatically installs:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

The two Dojo helpers remain beside KageLink and require no installed Python. Do not move or run those files separately.

KageLink automatically creates the access key and secure external connection. LeafOS integration is optional.

**Android**

1. Download `KageLink-Android.apk` on the phone.
2. Open the APK.
3. If Android asks for permission to install apps from that source, allow the source you are using to open the file.
4. Install and open KageLink.
5. On the PC, copy the address and access key shown by KageLink and use them to create the connection in the app.
6. Use the **Dojo** area to start, stop and follow training running on Windows.

The APK is a remote interface: vision, decisions and keyboard commands continue to run only in the PC Agent.

### Verify the download

The same Release includes `SHA256SUMS.txt` with the SHA-256 hashes of both official files.

**[Open the latest Release](https://github.com/leafoss/KageLink/releases/latest)**

For complete documentation, see the [English README](README.md) and the [3.5 Dojo guide](KAGELINK_3_5_DOJO.en.md).
