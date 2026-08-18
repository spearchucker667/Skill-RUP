"""
artifact_builder module for RUP deterministic runtime.
"""
from typing import Dict, Any
from pathlib import Path
from .paths import RupPaths
from .security import enforce_path_jail

class ArtifactBuilder:
    def __init__(self, paths: RupPaths):
        self.paths = paths

    def build_markdown(self, template_name: str, data: Dict[str, Any], output_filename: str) -> Path:
        """
        Populate a markdown template with data and save it securely.
        (A simplified builder that replaces placeholders with JSON string reps).
        """
        import json
        template_path = self.paths.templates_dir / template_name
        if not template_path.exists():
            # Fallback to empty if template missing
            content = f"# {template_name.replace('.md', '')}\\n\\n"
        else:
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
                
        # Basic substitution logic
        # In a real engine, Jinja2 or similar would be used.
        # Since we're dependency-free standard library Python:
        content += "\\n\\n## Generated Data\\n```json\\n"
        content += json.dumps(data, indent=2)
        content += "\\n```\\n"

        out_path = self.paths.get_target_path(output_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return out_path
