from abc import ABC, abstractmethod


class EmailProvider(ABC):
    @abstractmethod
    def send(self, recipient: str, subject: str, html_body: str, text_body: str) -> None:
        raise NotImplementedError
