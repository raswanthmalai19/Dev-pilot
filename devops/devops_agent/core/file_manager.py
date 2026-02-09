"""
File system management for DevOps Automation Agent.
Handles file operations, project scanning, and template rendering.
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
import aiofiles
import aiofiles.os
from jinja2 import Environment, FileSystemLoader, BaseLoader
from .logger import AgentLogger


class FileManager:
    """Manages file system operations for the agent."""
    
    def __init__(self, base_dir: Path = None, logger: AgentLogger = None):
        self.base_dir = base_dir or Path.cwd()
        self.logger = logger or AgentLogger("FileManager")
        
        # Setup Jinja2 for template rendering
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.base_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    
    async def read_file(self, path: Path) -> str:
        """Read file contents asynchronously."""
        full_path = self._resolve_path(path)
        try:
            async with aiofiles.open(full_path, 'r') as f:
                return await f.read()
        except Exception as e:
            self.logger.error(f"Failed to read {full_path}: {e}")
            raise
    
    async def write_file(self, path: Path, content: str, create_dirs: bool = True) -> None:
        """Write content to a file asynchronously."""
        full_path = self._resolve_path(path)
        try:
            if create_dirs:
                await aiofiles.os.makedirs(full_path.parent, exist_ok=True)
            async with aiofiles.open(full_path, 'w') as f:
                await f.write(content)
            self.logger.debug(f"Written to {full_path}")
        except Exception as e:
            self.logger.error(f"Failed to write {full_path}: {e}")
            raise
    
    async def copy_file(self, src: Path, dst: Path) -> None:
        """Copy a file asynchronously."""
        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)
        try:
            await aiofiles.os.makedirs(dst_path.parent, exist_ok=True)
            # Use sync copy for simplicity (could use aiofiles for large files)
            shutil.copy2(src_path, dst_path)
            self.logger.debug(f"Copied {src_path} to {dst_path}")
        except Exception as e:
            self.logger.error(f"Failed to copy {src_path} to {dst_path}: {e}")
            raise
    
    async def delete_file(self, path: Path) -> None:
        """Delete a file asynchronously."""
        full_path = self._resolve_path(path)
        try:
            await aiofiles.os.remove(full_path)
            self.logger.debug(f"Deleted {full_path}")
        except Exception as e:
            self.logger.error(f"Failed to delete {full_path}: {e}")
            raise
    
    async def exists(self, path: Path) -> bool:
        """Check if a path exists."""
        full_path = self._resolve_path(path)
        return await aiofiles.os.path.exists(full_path)
    
    async def is_file(self, path: Path) -> bool:
        """Check if path is a file."""
        full_path = self._resolve_path(path)
        return await aiofiles.os.path.isfile(full_path)
    
    async def is_dir(self, path: Path) -> bool:
        """Check if path is a directory."""
        full_path = self._resolve_path(path)
        return await aiofiles.os.path.isdir(full_path)
    
    async def list_dir(self, path: Path = None) -> List[Path]:
        """List contents of a directory."""
        full_path = self._resolve_path(path) if path else self.base_dir
        try:
            entries = await aiofiles.os.listdir(full_path)
            return [Path(full_path) / entry for entry in entries]
        except Exception as e:
            self.logger.error(f"Failed to list {full_path}: {e}")
            raise
    
    async def find_files(
        self, 
        pattern: str = "*", 
        path: Path = None,
        recursive: bool = True,
        exclude_dirs: List[str] = None
    ) -> List[Path]:
        """Find files matching a pattern."""
        search_path = self._resolve_path(path) if path else self.base_dir
        exclude_dirs = exclude_dirs or [".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist", "build"]
        
        files = []
        if recursive:
            for root, dirs, filenames in os.walk(search_path):
                # Exclude specified directories
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                
                root_path = Path(root)
                for filename in filenames:
                    file_path = root_path / filename
                    if file_path.match(pattern):
                        files.append(file_path)
        else:
            for entry in await self.list_dir(search_path):
                if entry.is_file() and entry.match(pattern):
                    files.append(entry)
        
        return files
    
    async def create_directory(self, path: Path) -> None:
        """Create a directory and its parents."""
        full_path = self._resolve_path(path)
        await aiofiles.os.makedirs(full_path, exist_ok=True)
        self.logger.debug(f"Created directory {full_path}")
    
    async def scan_project(self, path: Path = None) -> Dict[str, Any]:
        """
        Scan a project directory and return file inventory.
        Useful for project analysis.
        """
        scan_path = self._resolve_path(path) if path else self.base_dir
        
        result = {
            "root": str(scan_path),
            "files": [],
            "directories": [],
            "file_count": 0,
            "extensions": {},
        }
        
        exclude_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist", "build", ".idea", ".vscode"}
        
        for root, dirs, files in os.walk(scan_path):
            # Exclude common non-essential directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            rel_root = Path(root).relative_to(scan_path)
            
            for d in dirs:
                result["directories"].append(str(rel_root / d))
            
            for f in files:
                file_path = rel_root / f
                result["files"].append(str(file_path))
                result["file_count"] += 1
                
                # Track extensions
                ext = Path(f).suffix.lower()
                if ext:
                    result["extensions"][ext] = result["extensions"].get(ext, 0) + 1
        
        return result
    
    def render_template(self, template_str: str, context: Dict[str, Any]) -> str:
        """Render a Jinja2 template string with context."""
        template = self.jinja_env.from_string(template_str)
        return template.render(**context)
    
    async def render_template_file(
        self, 
        template_path: Path, 
        output_path: Path, 
        context: Dict[str, Any]
    ) -> None:
        """Render a template file and write to output."""
        template_content = await self.read_file(template_path)
        rendered = self.render_template(template_content, context)
        await self.write_file(output_path, rendered)
    
    def _resolve_path(self, path: Path) -> Path:
        """Resolve a path relative to base_dir if not absolute."""
        if path is None:
            return self.base_dir
        path = Path(path) if isinstance(path, str) else path
        if path.is_absolute():
            return path
        return self.base_dir / path
    
    async def get_file_size(self, path: Path) -> int:
        """Get file size in bytes."""
        full_path = self._resolve_path(path)
        stat = await aiofiles.os.stat(full_path)
        return stat.st_size
    
    async def copy_directory(self, src: Path, dst: Path) -> None:
        """Copy a directory recursively."""
        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)
        try:
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            self.logger.debug(f"Copied directory {src_path} to {dst_path}")
        except Exception as e:
            self.logger.error(f"Failed to copy directory {src_path}: {e}")
            raise
