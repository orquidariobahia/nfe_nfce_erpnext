from abc import ABC, abstractmethod

class BaseFiscalProvider(ABC):
    """
    Abstract Base Class for Fiscal Document Providers (e.g., WebManiaBR, SEFAZ Direct).
    """

    @abstractmethod
    def get_settings(self) -> dict:
        """Return provider configuration settings/credentials dict."""
        pass

    @abstractmethod
    def emit_nota_fiscal(self, payload: dict) -> dict:
        """
        Sends payload to fiscal provider API for NFe / NFCe emission.
        Returns response dictionary from provider.
        """
        pass

    @abstractmethod
    def cancel_nota_fiscal(self, chave: str, motivo: str) -> dict:
        """
        Cancels an emitted fiscal document by key and reason.
        Returns cancellation response dictionary.
        """
        pass

    @abstractmethod
    def get_danfe_url(self, chave: str, format_type: str = "danfe") -> str:
        """
        Returns URL for DANFE PDF / thermal / XML download.
        format_type options: 'danfe', 'simples', 'etiqueta', 'xml'
        """
        pass
