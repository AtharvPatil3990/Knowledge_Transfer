from dataclasses import dataclass
from typing import Protocol

import httpx


class SourceConnector(Protocol):
    def fetch(self, repository: str, state: str, limit: int) -> list[dict]:
        ...


@dataclass(frozen=True)
class GitHubConnector:
    token: str | None = None
    api_url: str = "https://api.github.com"

    def fetch(self, repository: str, state: str = "open", limit: int = 20) -> list[dict]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with httpx.Client(base_url=self.api_url, headers=headers, timeout=30.0) as client:
            response = client.get(
                f"/repos/{repository}/pulls",
                params={"state": state, "per_page": limit},
            )
            response.raise_for_status()
            pull_requests = response.json()

            documents = []
            for pull_request in pull_requests:
                details = client.get(
                    f"/repos/{repository}/pulls/{pull_request['number']}"
                )
                details.raise_for_status()
                pull = details.json()

                comments = client.get(
                    f"/repos/{repository}/issues/{pull_request['number']}/comments"
                )
                comments.raise_for_status()

                documents.append({
                    "source_id": f"PR-{pull['number']}",
                    "source_url": pull["html_url"],
                    "title": pull["title"],
                    "content": self._content(pull, comments.json()),
                    "metadata": {
                        "repository": repository,
                        "number": pull["number"],
                        "state": pull["state"],
                        "author": (pull.get("user") or {}).get("login"),
                        "labels": [label["name"] for label in pull.get("labels", [])],
                        "head_branch": pull.get("head", {}).get("ref"),
                        "base_branch": pull.get("base", {}).get("ref"),
                    },
                })
            return documents

    @staticmethod
    def _content(pull: dict, comments: list[dict]) -> str:
        sections = [
            f"Pull request: {pull['title']}",
            f"Description:\n{pull.get('body') or '(no description)'}",
        ]
        if comments:
            sections.append("Discussion:")
            sections.extend(
                f"{comment.get('user', {}).get('login', 'unknown')}: "
                f"{comment.get('body') or ''}"
                for comment in comments
            )
        return "\n\n".join(sections)
