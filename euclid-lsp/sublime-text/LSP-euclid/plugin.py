from LSP.plugin import LspPlugin, ServerConfig, Session
from lsp.utils import thinclient
import sublime


class LspEuclidPlugin(LspPlugin):
    """LSP client plugin for Euclid-IR language server."""

    server_name = "euclid-lsp"

    @classmethod
    def server_config(cls) -> ServerConfig:
        return ServerConfig(
            name=cls.server_name,
            command=["euclid-lsp"],
            selector="source.euclid",
            env={},
            initialization_options={},
        )


plugin_loaded = LspEuclidPlugin.register
plugin_unloaded = LspEuclidPlugin.unregister
