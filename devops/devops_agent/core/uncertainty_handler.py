"""
Uncertainty Handler - Autonomous decision-making for ambiguous situations.

This module handles cases where the system cannot determine clear answers:
- Unknown project types
- Ambiguous configurations
- Missing critical information
- Conflicting signals
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List
from pathlib import Path

from ..core.logger import get_logger
from ..core.gemini_client import GeminiClient


class UncertaintyLevel(Enum):
    """Level of uncertainty in analysis."""
    CONFIDENT = "confident"  # >90% confident
    LIKELY = "likely"  # 70-90% confident
    UNCERTAIN = "uncertain"  # 40-70% confident
    AMBIGUOUS = "ambiguous"  # <40% confident


class ResolutionStrategy(Enum):
    """Strategy for resolving uncertainty."""
    HEURISTIC = "heuristic"  # Use rules and patterns
    AI_ANALYSIS = "ai_analysis"  # Ask Gemini AI
    DEFAULT_FALLBACK = "default_fallback"  # Use safe defaults
    MANUAL_INTERVENTION = "manual_intervention"  # Escalate to human


@dataclass
class AnalysisResult:
    """Result of uncertainty resolution."""
    resolved: bool
    confidence: UncertaintyLevel
    value: Any
    reasoning: str = ""
    alternatives: List[Any] = field(default_factory=list)
    strategy_used: Optional[ResolutionStrategy] = None


class UncertaintyHandler:
    """
    Handles uncertain situations in autonomous deployment.
    
    Uses multiple strategies to resolve ambiguities:
    1. Heuristics (file patterns, conventions)
    2. AI Analysis (Gemini reasoning)
    3. Safe defaults
    4. Manual escalation (last resort)
    """
    
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        """Initialize uncertainty handler."""
        self.logger = get_logger("UncertaintyHandler")
        self.gemini = gemini_client or GeminiClient()
        
    async def resolve_project_type(
        self,
        project_path: Path,
        file_patterns: Dict[str, int],
    ) -> AnalysisResult:
        """
        Resolve uncertain project type.
        
        Args:
            project_path: Path to analyze
            file_patterns: Counts of files by extension
            
        Returns:
            AnalysisResult with determined project type
        """
        self.logger.info("Resolving project type uncertainty")
        
        # Strategy 1: Heuristics based on file counts
        dominant_type = self._determine_dominant_language(file_patterns)
        if dominant_type:
            return AnalysisResult(
                resolved=True,
                confidence=UncertaintyLevel.CONFIDENT,
                value=dominant_type,
                reasoning=f"Dominant file type: {dominant_type}",
                strategy_used=ResolutionStrategy.HEURISTIC,
            )
        
        # Strategy 2: AI Analysis
        try:
            ai_result = await self._ask_gemini_project_type(project_path)
            if ai_result:
                return AnalysisResult(
                    resolved=True,
                    confidence=UncertaintyLevel.LIKELY,
                    value=ai_result["type"],
                    reasoning=ai_result.get("reasoning", "AI analysis"),
                    strategy_used=ResolutionStrategy.AI_ANALYSIS,
                )
        except Exception as e:
            self.logger.warning(f"AI analysis failed: {e}")
        
        # Strategy 3: Default fallback
        return AnalysisResult(
            resolved=False,
            confidence=UncertaintyLevel.AMBIGUOUS,
            value=None,
            reasoning="Could not determine project type",
            strategy_used=ResolutionStrategy.MANUAL_INTERVENTION,
        )
    
    async def resolve_port(
        self,
        project_path: Path,
        detected_framework: str = None,
        code_samples: List[str] = None,
    ) -> AnalysisResult:
        """
        Resolve uncertain port number.
        
        Args:
            project_path: Project directory
            detected_framework: Framework if known
            code_samples: Sample code to analyze
            
        Returns:
            AnalysisResult with port number
        """
        self.logger.info("Resolving port number")
        
        # Strategy 1: Framework defaults
        framework_ports = {
            "flask": 5000,
            "fastapi": 8000,
            "express": 3000,
            "spring": 8080,
            "spring_boot": 8080,
            "django": 8000,
            "streamlit": 8501,
            "gradio": 7860,
        }
        
        if detected_framework and detected_framework.lower() in framework_ports:
            port = framework_ports[detected_framework.lower()]
            return AnalysisResult(
                resolved=True,
                confidence=UncertaintyLevel.CONFIDENT,
                value=port,
                reasoning=f"Framework default for {detected_framework}",
                strategy_used=ResolutionStrategy.HEURISTIC,
            )
        
        # Strategy 2: Code analysis for listen() or PORT usage
        if code_samples:
            for code in code_samples:
                port = self._extract_port_from_code(code)
                if port:
                    return AnalysisResult(
                        resolved=True,
                        confidence=UncertaintyLevel.LIKELY,
                        value=port,
                        reasoning="Extracted from code",
                        strategy_used=ResolutionStrategy.HEURISTIC,
                    )
        
        # Strategy 3: AI analysis
        if code_samples:
            try:
                ai_port = await self._ask_gemini_port(code_samples)
                if ai_port:
                    return AnalysisResult(
                        resolved=True,
                        confidence=UncertaintyLevel.LIKELY,
                        value=ai_port,
                        reasoning="AI-determined from code analysis",
                        strategy_used=ResolutionStrategy.AI_ANALYSIS,
                    )
            except Exception as e:
                self.logger.warning(f"AI port analysis failed: {e}")
        
        # Strategy 4: Safe default
        return AnalysisResult(
            resolved=True,
            confidence=UncertaintyLevel.UNCERTAIN,
            value=8080,
            reasoning="Using safe default port 8080",
            strategy_used=ResolutionStrategy.DEFAULT_FALLBACK,
        )
    
    async def resolve_start_command(
        self,
        project_type: str,
        framework: str = None,
        entry_point: str = None,
        package_file_content: str = None,
    ) -> AnalysisResult:
        """
        Resolve uncertain start command.
        
        Args:
            project_type: Detected project type
            framework: Framework if known
            entry_point: Entry point file
            package_file_content: Content of package.json, requirements.txt, etc.
            
        Returns:
            AnalysisResult with start command
        """
        self.logger.info("Resolving start command")
        
        # Strategy 1: Framework-specific commands
        if framework:
            cmd = self._get_framework_start_command(project_type, framework, entry_point)
            if cmd:
                return AnalysisResult(
                    resolved=True,
                    confidence=UncertaintyLevel.CONFIDENT,
                    value=cmd,
                    reasoning=f"Standard command for {framework}",
                    strategy_used=ResolutionStrategy.HEURISTIC,
                )
        
        # Strategy 2: Package file analysis
        if package_file_content:
            cmd = self._extract_start_from_package(project_type, package_file_content)
            if cmd:
                return AnalysisResult(
                    resolved=True,
                    confidence=UncertaintyLevel.CONFIDENT,
                    value=cmd,
                    reasoning="Found in package configuration",
                    strategy_used=ResolutionStrategy.HEURISTIC,
                )
        
        # Strategy 3: AI analysis
        try:
            ai_cmd = await self._ask_gemini_start_command(
                project_type, framework, entry_point, package_file_content
            )
            if ai_cmd:
                return AnalysisResult(
                    resolved=True,
                    confidence=UncertaintyLevel.LIKELY,
                    value=ai_cmd,
                    reasoning="AI-recommended command",
                    strategy_used=ResolutionStrategy.AI_ANALYSIS,
                )
        except Exception as e:
            self.logger.warning(f"AI start command analysis failed: {e}")
        
        # Strategy 4: Generic fallback
        generic_cmd = self._get_generic_start_command(project_type, entry_point)
        return AnalysisResult(
            resolved=True,
            confidence=UncertaintyLevel.UNCERTAIN,
            value=generic_cmd,
            reasoning="Generic command for project type",
            strategy_used=ResolutionStrategy.DEFAULT_FALLBACK,
        )
    
    def _determine_dominant_language(self, file_patterns: Dict[str, int]) -> Optional[str]:
        """Determine dominant language from file counts."""
        if not file_patterns:
            return None
        
        # Language file extensions
        lang_map = {
            "python": [".py"],
            "nodejs": [".js", ".ts", ".jsx", ".tsx"],
            "go": [".go"],
            "java": [".java"],
            "rust": [".rs"],
        }
        
        # Count files per language
        lang_counts = {}
        for lang, extensions in lang_map.items():
            count = sum(file_patterns.get(ext, 0) for ext in extensions)
            if count > 0:
                lang_counts[lang] = count
        
        if not lang_counts:
            return None
        
        # Get dominant (must be >50% of total or clear winner)
        total = sum(lang_counts.values())
        dominant = max(lang_counts.items(), key=lambda x: x[1])
        
        if dominant[1] / total > 0.5 or dominant[1] > total * 0.4:
            return dominant[0]
        
        return None
    
    def _extract_port_from_code(self, code: str) -> Optional[int]:
        """Extract port number from code patterns."""
        import re
        
        # Common patterns
        patterns = [
            r"\.listen\((\d+)",  # app.listen(3000)
            r"PORT\s*=\s*(\d+)",  # PORT = 8080
            r"port\s*=\s*(\d+)",  # port = 5000
            r"--port[= ](\d+)",  # --port=8000
        ]
        
        for pattern in patterns:
            match = re.search(pattern, code)
            if match:
                try:
                    port = int(match.group(1))
                    if 1 <= port <= 65535:
                        return port
                except ValueError:
                    pass
        
        return None
    
    def _get_framework_start_command(
        self,
        project_type: str,
        framework: str,
        entry_point: str = None,
    ) -> Optional[str]:
        """Get standard start command for framework."""
        commands = {
            ("python", "flask"): f"flask run --host 0.0.0.0 --port 8080",
            ("python", "fastapi"): f"uvicorn {entry_point or 'main'}:app --host 0.0.0.0 --port 8080",
            ("python", "django"): "python manage.py runserver 0.0.0.0:8080",
            ("python", "streamlit"): f"streamlit run {entry_point or 'app.py'} --server.port 8080",
            ("nodejs", "express"): "node index.js",
            ("nodejs", None): "npm start",
            ("go", None): "./app",
            ("rust", None): "./target/release/app",
        }
        
        return commands.get((project_type.lower(), framework.lower() if framework else None))
    
    def _extract_start_from_package(self, project_type: str, content: str) -> Optional[str]:
        """Extract start command from package file."""
        import json
        
        if project_type.lower() == "nodejs":
            try:
                package = json.loads(content)
                scripts = package.get("scripts", {})
                return scripts.get("start")
            except:
                pass
        
        return None
    
    def _get_generic_start_command(self, project_type: str, entry_point: str = None) -> str:
        """Get generic start command for project type."""
        commands = {
            "python": f"python {entry_point or 'main.py'}",
            "nodejs": "node index.js",
            "go": "./app",
            "java": "java -jar app.jar",
            "rust": "./app",
        }
        return commands.get(project_type.lower(), "npm start")
    
    async def _ask_gemini_project_type(self, project_path: Path) -> Optional[Dict[str, Any]]:
        """Ask Gemini AI to determine project type."""
        # List files
        files = list(project_path.rglob("*"))[:50]  # Limit for context window
        file_list = "\\n".join([f.name for f in files if f.is_file()])
        
        prompt = f"""Analyze this project structure and determine the project type.

Files:
{file_list}

Return JSON with:
- type: "python", "nodejs", "go", "java", or "rust"
- confidence: 0.0 to 1.0
- reasoning: brief explanation

Return ONLY valid JSON."""
        
        try:
            response = await self.gemini.generate(prompt, enable_tools=False)
            import json
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\\n", 1)[1]
            if response.endswith("```"):
                response = response.rsplit("```", 1)[0]
            return json.loads(response.strip())
        except:
            return None
    
    async def _ask_gemini_port(self, code_samples: List[str]) -> Optional[int]:
        """Ask Gemini AI to determine port from code."""
        combined_code = "\\n\\n".join(code_samples[:3])  # Limit samples
        
        prompt = f"""Analyze this code and determine what port the application listens on.

Code:
```
{combined_code}
```

Return ONLY the port number as a single integer, nothing else."""
        
        try:
            response = await self.gemini.generate(prompt, enable_tools=False)
            port = int(response.strip())
            if 1 <= port <= 65535:
                return port
        except:
            pass
        
        return None
    
    async def _ask_gemini_start_command(
        self,
        project_type: str,
        framework: str = None,
        entry_point: str = None,
        package_content: str = None,
    ) -> Optional[str]:
        """Ask Gemini AI to determine start command."""
        context = {
            "project_type": project_type,
            "framework": framework,
            "entry_point": entry_point,
        }
        
        if package_content:
            context["package_file"] = package_content[:500]  # Truncate
        
        import json
        prompt = f"""Determine the command to start this application.

Context:
```json
{json.dumps(context, indent=2)}
```

Return ONLY the command string, nothing else. Example: "uvicorn main:app --host 0.0.0.0 --port 8080"
"""
        
        try:
            response = await self.gemini.generate(prompt, enable_tools=False)
            return response.strip()
        except:
            return None
