const path = require("path");
const { workspace } = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function activate(context) {
  const serverModule = workspace
    .getConfiguration("euclid")
    .get("serverPath", "euclid-lsp");

  const serverOptions = {
    command: serverModule,
    args: [],
    transport: TransportKind.stdio,
  };

  const clientOptions = {
    documentSelector: [{ scheme: "file", language: "euclid" }],
    synchronize: {
      fileEvents: workspace.createFileSystemWatcher("**/*.euclid"),
    },
  };

  client = new LanguageClient(
    "euclid",
    "Euclid-IR Language Server",
    serverOptions,
    clientOptions
  );

  client.start();
}

function deactivate() {
  if (client) {
    return client.stop();
  }
}

module.exports = { activate, deactivate };
