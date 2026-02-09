"""
Project Analyzer Agent - Detects project type, framework, and configuration.
Uses Gemini for intelligent analysis of complex projects.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent
from ..models.project import (
    ProjectInfo, ProjectType, Framework, Dependency,
    PROJECT_SIGNATURES, FRAMEWORK_SIGNATURES
)


class ProjectAnalyzer(BaseAgent):
    """
    Analyzes a project directory to detect:
    - Programming language and version
    - Framework being used
    - Entry points
    - Dependencies
    - Build/start commands
    - Environment requirements
    """
    
    def __init__(self, working_dir: Path = None, gemini_client=None):
        super().__init__("ProjectAnalyzer", working_dir, gemini_client)
    
    def _get_system_instruction(self) -> str:
        return """You are an expert code analyst. You analyze project structures, 
detect frameworks, understand entry points, and identify build requirements.
Be precise and return structured JSON when requested."""
    
    async def run(self, project_path: Path) -> ProjectInfo:
        """
        Analyze a project and return complete ProjectInfo.
        
        Args:
            project_path: Path to the project directory
            
        Returns:
            ProjectInfo with all detected information
        """
        self.log_step("Starting project analysis", 1)
        
        project_path = Path(project_path)
        if not project_path.exists():
            raise ValueError(f"Project path does not exist: {project_path}")
        
        # Scan the project directory
        self.log_step("Scanning project files", 2)
        scan_result = await self.file_manager.scan_project(project_path)
        
        # Detect project type
        self.log_step("Detecting project type", 3)
        project_type = await self._detect_project_type(project_path, scan_result)
        
        # Get project name
        project_name = project_path.name
        
        # Create initial ProjectInfo
        info = ProjectInfo(
            name=project_name,
            path=project_path,
            project_type=project_type,
            files=scan_result["files"][:100],  # Limit for context
            total_file_count=scan_result["file_count"],
        )
        
        # Detect package manager and dependencies
        self.log_step("Analyzing dependencies", 4)
        await self._analyze_dependencies(project_path, info)
        
        # Detect framework
        self.log_step("Detecting framework", 5)
        await self._detect_framework(info)
        
        # Use Gemini for deeper analysis
        self.log_step("Running AI analysis", 6)
        await self._gemini_analyze(project_path, info)
        
        # Determine build/start commands
        self.log_step("Determining build commands", 7)
        await self._determine_commands(info)
        
        self.log_success(f"Analysis complete: {info.project_type.value} / {info.framework.value}")
        
        return info
    
    async def _detect_project_type(
        self, 
        project_path: Path, 
        scan_result: Dict[str, Any]
    ) -> ProjectType:
        """Detect the primary project type based on signature files."""
        files_set = set(scan_result["files"])
        
        # Check each project type's signatures
        for proj_type, signatures in PROJECT_SIGNATURES.items():
            for sig in signatures:
                # Handle wildcards
                if "*" in sig:
                    pattern = sig.replace("*", "")
                    if any(f.endswith(pattern) for f in files_set):
                        return proj_type
                else:
                    if sig in files_set or any(f.endswith(f"/{sig}") or f == sig for f in files_set):
                        return proj_type
        
        return ProjectType.UNKNOWN
    
    async def _analyze_dependencies(self, project_path: Path, info: ProjectInfo) -> None:
        """Analyze project dependencies based on package manager files."""
        
        if info.project_type == ProjectType.PYTHON:
            await self._analyze_python_deps(project_path, info)
        elif info.project_type == ProjectType.NODEJS:
            await self._analyze_nodejs_deps(project_path, info)
        elif info.project_type == ProjectType.GO:
            await self._analyze_go_deps(project_path, info)
        elif info.project_type == ProjectType.JAVA:
            await self._analyze_java_deps(project_path, info)
        elif info.project_type == ProjectType.RUST:
            await self._analyze_rust_deps(project_path, info)
    
    async def _analyze_python_deps(self, project_path: Path, info: ProjectInfo) -> None:
        """Analyze Python dependencies."""
        deps = []
        
        # Check requirements.txt
        req_file = project_path / "requirements.txt"
        if req_file.exists():
            info.package_manager = "pip"
            content = await self.file_manager.read_file(req_file)
            for line in content.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    # Parse package==version or package>=version etc
                    match = re.match(r'^([a-zA-Z0-9_-]+)([<>=!]+)?(.+)?', line.split(";")[0])
                    if match:
                        deps.append(Dependency(
                            name=match.group(1),
                            version=match.group(3) if match.group(3) else None
                        ))
        
        # Check pyproject.toml
        pyproject_file = project_path / "pyproject.toml"
        if pyproject_file.exists():
            info.package_manager = info.package_manager or "poetry"
            # Parse pyproject.toml for dependencies (simplified)
            content = await self.file_manager.read_file(pyproject_file)
            # Look for python version
            version_match = re.search(r'python\s*=\s*"([^"]+)"', content)
            if version_match:
                info.language_version = version_match.group(1)
        
        info.dependencies = deps
    
    async def _analyze_nodejs_deps(self, project_path: Path, info: ProjectInfo) -> None:
        """Analyze Node.js dependencies."""
        package_file = project_path / "package.json"
        
        if package_file.exists():
            content = await self.file_manager.read_file(package_file)
            try:
                pkg = json.loads(content)
                
                # Determine package manager
                if (project_path / "yarn.lock").exists():
                    info.package_manager = "yarn"
                elif (project_path / "pnpm-lock.yaml").exists():
                    info.package_manager = "pnpm"
                else:
                    info.package_manager = "npm"
                
                # Get name
                if "name" in pkg:
                    info.name = pkg["name"]
                
                # Parse dependencies
                deps = []
                for dep_type in ["dependencies", "devDependencies"]:
                    for name, version in pkg.get(dep_type, {}).items():
                        deps.append(Dependency(
                            name=name,
                            version=version,
                            dev=(dep_type == "devDependencies")
                        ))
                info.dependencies = deps
                
                # Get scripts
                scripts = pkg.get("scripts", {})
                if "start" in scripts:
                    info.start_command = f"{info.package_manager} start"
                if "build" in scripts:
                    info.build_command = f"{info.package_manager} run build"
                if "test" in scripts:
                    info.test_command = f"{info.package_manager} test"
                
                # Get main entry point
                if "main" in pkg:
                    info.main_file = pkg["main"]
                
                # Get engines for version
                if "engines" in pkg and "node" in pkg["engines"]:
                    info.language_version = pkg["engines"]["node"]
                    
            except json.JSONDecodeError:
                self.logger.warning("Failed to parse package.json")
    
    async def _analyze_go_deps(self, project_path: Path, info: ProjectInfo) -> None:
        """Analyze Go dependencies."""
        go_mod = project_path / "go.mod"
        
        if go_mod.exists():
            info.package_manager = "go modules"
            content = await self.file_manager.read_file(go_mod)
            
            # Get Go version
            version_match = re.search(r'go\s+(\d+\.\d+)', content)
            if version_match:
                info.language_version = version_match.group(1)
            
            # Parse requires
            deps = []
            for match in re.finditer(r'^\s*([^\s]+)\s+v([^\s]+)', content, re.MULTILINE):
                deps.append(Dependency(name=match.group(1), version=match.group(2)))
            info.dependencies = deps
    
    async def _analyze_java_deps(self, project_path: Path, info: ProjectInfo) -> None:
        """Analyze Java dependencies."""
        pom_file = project_path / "pom.xml"
        gradle_file = project_path / "build.gradle"
        
        if pom_file.exists():
            info.package_manager = "maven"
            info.build_command = "mvn package -DskipTests"
        elif gradle_file.exists():
            info.package_manager = "gradle"
            info.build_command = "./gradlew build -x test"
    
    async def _analyze_rust_deps(self, project_path: Path, info: ProjectInfo) -> None:
        """Analyze Rust dependencies."""
        cargo_file = project_path / "Cargo.toml"
        
        if cargo_file.exists():
            info.package_manager = "cargo"
            info.build_command = "cargo build --release"
            content = await self.file_manager.read_file(cargo_file)
            
            # Get package name
            name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
            if name_match:
                info.name = name_match.group(1)
    
    async def _detect_framework(self, info: ProjectInfo) -> None:
        """Detect the framework based on dependencies and files."""
        dep_names = {d.name.lower() for d in info.dependencies}
        
        for framework, signatures in FRAMEWORK_SIGNATURES.items():
            # Check if any required dependency is present
            required_deps = {d.lower() for d in signatures.get("deps", [])}
            if required_deps and required_deps.intersection(dep_names):
                info.framework = framework
                info.is_web_service = True
                return
        
        # Default port assignments based on framework
        if info.framework in [Framework.FLASK, Framework.FASTAPI, Framework.DJANGO]:
            info.port = 8000
        elif info.framework in [Framework.EXPRESS, Framework.NEXTJS]:
            info.port = 3000
        elif info.framework in [Framework.SPRING, Framework.SPRING_BOOT]:
            info.port = 8080
    
    async def _gemini_analyze(self, project_path: Path, info: ProjectInfo) -> None:
        """Use Gemini for deeper analysis of the project."""
        # Read main entry files for context
        main_files_content = await self._get_main_files_content(project_path, info)
        
        if not main_files_content:
            return
        
        prompt = f"""Analyze this project and return a JSON object:

Project Type: {info.project_type.value}
Dependencies: {[d.name for d in info.dependencies[:20]]}

Main Files:
{main_files_content}

Return JSON with:
- entry_point: main file/entry point
- port: port number if web service (integer)
- is_web_service: true/false
- health_endpoint: health check endpoint if exists
- start_command: command to start the app
- required_env_vars: list of required environment variables
- purpose: one line description

Return ONLY valid JSON."""

        try:
            response = await self.gemini.generate(prompt, enable_tools=False)
            
            # Parse response
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1]
            if response.endswith("```"):
                response = response.rsplit("```", 1)[0]
            
            analysis = json.loads(response.strip())
            
            # Update info with analysis
            if "entry_point" in analysis:
                info.entry_point = analysis["entry_point"]
            if "port" in analysis and isinstance(analysis["port"], int):
                info.port = analysis["port"]
            if "is_web_service" in analysis:
                info.is_web_service = analysis["is_web_service"]
            if "health_endpoint" in analysis:
                info.health_endpoint = analysis["health_endpoint"]
            if "start_command" in analysis and not info.start_command:
                info.start_command = analysis["start_command"]
            if "required_env_vars" in analysis:
                info.required_env_vars = analysis["required_env_vars"]
            
            info.gemini_analysis = analysis
            
        except Exception as e:
            self.logger.warning(f"Gemini analysis failed: {e}")
    
    async def _get_main_files_content(self, project_path: Path, info: ProjectInfo) -> str:
        """Get content of main entry files for analysis."""
        main_files = []
        
        # Determine which files to read based on project type
        if info.project_type == ProjectType.PYTHON:
            candidates = ["main.py", "app.py", "run.py", "server.py", "__init__.py", "wsgi.py"]
        elif info.project_type == ProjectType.NODEJS:
            candidates = ["index.js", "app.js", "server.js", "main.js", "index.ts", "app.ts"]
        elif info.project_type == ProjectType.GO:
            candidates = ["main.go", "cmd/main.go"]
        elif info.project_type == ProjectType.JAVA:
            candidates = ["Application.java", "Main.java"]
        elif info.project_type == ProjectType.RUST:
            candidates = ["main.rs", "lib.rs"]
        else:
            return ""
        
        for candidate in candidates:
            file_path = project_path / candidate
            if file_path.exists():
                try:
                    content = await self.file_manager.read_file(file_path)
                    # Limit content size
                    if len(content) > 3000:
                        content = content[:3000] + "\n... (truncated)"
                    main_files.append(f"=== {candidate} ===\n{content}")
                except Exception:
                    pass
        
        return "\n\n".join(main_files[:2])  # Limit to 2 files
    
    async def _determine_commands(self, info: ProjectInfo) -> None:
        """Determine build/start/test commands based on project type."""
        
        if info.project_type == ProjectType.PYTHON:
            if not info.build_command:
                info.build_command = "pip install -r requirements.txt"
            if not info.start_command:
                if info.framework == Framework.FASTAPI:
                    info.start_command = f"uvicorn {info.entry_point or 'main'}:app --host 0.0.0.0 --port {info.port}"
                elif info.framework == Framework.FLASK:
                    info.start_command = f"flask run --host 0.0.0.0 --port {info.port}"
                elif info.framework == Framework.STREAMLIT:
                    info.start_command = f"streamlit run {info.entry_point or 'app.py'} --server.port {info.port}"
                elif info.entry_point:
                    info.start_command = f"python {info.entry_point}"
            if not info.test_command:
                info.test_command = "pytest"
        
        elif info.project_type == ProjectType.NODEJS:
            if not info.build_command:
                info.build_command = f"{info.package_manager} install"
            if not info.start_command:
                info.start_command = f"{info.package_manager} start"
        
        elif info.project_type == ProjectType.GO:
            if not info.build_command:
                info.build_command = "go build -o app ."
            if not info.start_command:
                info.start_command = "./app"
            if not info.test_command:
                info.test_command = "go test ./..."
        
        elif info.project_type == ProjectType.RUST:
            if not info.build_command:
                info.build_command = "cargo build --release"
            if not info.start_command:
                info.start_command = f"./target/release/{info.name}"
            if not info.test_command:
                info.test_command = "cargo test"
