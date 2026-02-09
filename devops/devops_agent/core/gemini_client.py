"""
Gemini LLM Client for DevOps Automation Agent.
Provides function calling capabilities for agentic workflows.
"""

import json
from typing import Any, Dict, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

from ..config import get_config
from .logger import AgentLogger


@dataclass
class ToolDefinition:
    """Definition of a tool that Gemini can call."""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Awaitable[Any]]


class GeminiClient:
    """
    Gemini API client with function calling support.
    Enables agentic workflows where Gemini can invoke tools.
    """
    
    def __init__(self, system_instruction: str = None):
        self.config = get_config()
        self.logger = AgentLogger("GeminiClient")
        
        # Configure Gemini API
        if not self.config.gemini.api_key:
            raise ValueError("GEMINI_API_KEY is required")
        
        genai.configure(api_key=self.config.gemini.api_key)
        
        # Default system instruction for DevOps tasks
        self.system_instruction = system_instruction or """You are an expert DevOps automation agent. 
You analyze projects, create build configurations, Dockerfiles, CI/CD pipelines, and infrastructure code.
Be precise, follow best practices, and provide production-ready configurations.
When generating YAML, ensure proper indentation and valid syntax.
When generating Dockerfiles, use multi-stage builds and security best practices."""
        
        # Initialize model
        self.model = genai.GenerativeModel(
            model_name=self.config.gemini.model_name,
            system_instruction=self.system_instruction,
            generation_config=genai.GenerationConfig(
                temperature=self.config.gemini.temperature,
                max_output_tokens=self.config.gemini.max_output_tokens,
            )
        )
        
        # Tool registry
        self.tools: Dict[str, ToolDefinition] = {}
        
        # Conversation history for multi-turn
        self.chat_session = None
    
    def register_tool(
        self, 
        name: str, 
        description: str, 
        parameters: Dict[str, Any],
        handler: Callable[..., Awaitable[Any]]
    ) -> None:
        """Register a tool that Gemini can invoke."""
        self.tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
        )
        self.logger.debug(f"Registered tool: {name}")
    
    def _build_tools(self) -> List[Tool]:
        """Build Gemini Tool objects from registered tools."""
        if not self.tools:
            return []
        
        function_declarations = []
        for tool in self.tools.values():
            func_decl = FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
            )
            function_declarations.append(func_decl)
        
        return [Tool(function_declarations=function_declarations)]
    
    async def generate(
        self, 
        prompt: str,
        context: Dict[str, Any] = None,
        enable_tools: bool = True,
        max_tool_calls: int = 10,
    ) -> str:
        """
        Generate a response, automatically handling function calls.
        
        Args:
            prompt: The user prompt
            context: Additional context to include
            enable_tools: Whether to enable function calling
            max_tool_calls: Maximum number of tool calls to allow
            
        Returns:
            The final text response
        """
        # Build the full prompt with context
        full_prompt = prompt
        if context:
            context_str = json.dumps(context, indent=2)
            full_prompt = f"Context:\n```json\n{context_str}\n```\n\n{prompt}"
        
        # Get tools if enabled
        tools = self._build_tools() if enable_tools and self.tools else None
        
        try:
            response = self.model.generate_content(
                full_prompt,
                tools=tools,
            )
            
            # Handle function calls
            tool_call_count = 0
            while response.candidates[0].content.parts:
                # Check for function calls
                function_calls = [
                    part.function_call 
                    for part in response.candidates[0].content.parts 
                    if hasattr(part, 'function_call') and part.function_call.name
                ]
                
                if not function_calls:
                    break
                
                if tool_call_count >= max_tool_calls:
                    self.logger.warning(f"Reached max tool calls ({max_tool_calls})")
                    break
                
                # Execute function calls
                function_responses = []
                for fc in function_calls:
                    tool_call_count += 1
                    result = await self._execute_function_call(fc)
                    function_responses.append({
                        "name": fc.name,
                        "response": {"result": result}
                    })
                
                # Continue the conversation with function results
                response = self.model.generate_content(
                    [
                        full_prompt,
                        response.candidates[0].content,
                        {"function_response": function_responses}
                    ],
                    tools=tools,
                )
            
            # Extract final text response
            return self._extract_text(response)
            
        except Exception as e:
            self.logger.error(f"Generation failed: {e}", exc=e)
            raise
    
    async def _execute_function_call(self, function_call) -> Any:
        """Execute a function call from Gemini."""
        name = function_call.name
        args = dict(function_call.args) if function_call.args else {}
        
        self.logger.info(f"Executing tool: {name}", args=args)
        
        if name not in self.tools:
            raise ValueError(f"Unknown tool: {name}")
        
        tool = self.tools[name]
        try:
            result = await tool.handler(**args)
            self.logger.debug(f"Tool {name} completed successfully")
            return result
        except Exception as e:
            self.logger.error(f"Tool {name} failed: {e}", exc=e)
            return {"error": str(e)}
    
    def _extract_text(self, response) -> str:
        """Extract text from Gemini response."""
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    return part.text
            return ""
        except (IndexError, AttributeError):
            return ""
    
    async def analyze_code(self, code: str, file_path: str = None) -> Dict[str, Any]:
        """Analyze code and return structured insights."""
        prompt = f"""Analyze this code and return a JSON object with:
- language: programming language
- framework: framework if any (null if none)
- purpose: brief description of what the code does
- entry_point: main entry point if applicable
- dependencies: list of key dependencies mentioned
- port: port number if this is a web service

Code{f' ({file_path})' if file_path else ''}:
```
{code}
```

Return ONLY valid JSON, no markdown code blocks."""

        response = await self.generate(prompt, enable_tools=False)
        
        try:
            # Clean up response if needed
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1]
            if response.endswith("```"):
                response = response.rsplit("```", 1)[0]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse code analysis as JSON")
            return {"raw_response": response}
    
    async def generate_dockerfile(
        self, 
        project_info: Dict[str, Any],
        requirements: List[str] = None
    ) -> str:
        """Generate an optimized Dockerfile for a project."""
        prompt = f"""Generate a production-ready Dockerfile for this project:

Project Info:
```json
{json.dumps(project_info, indent=2)}
```

Requirements:
- Use multi-stage build for minimal image size
- Use specific version tags, not 'latest'
- Run as non-root user for security
- Include proper HEALTHCHECK if it's a web service
- Use .dockerignore patterns
- Optimize layer caching

Return ONLY the Dockerfile content, no explanations or markdown code blocks."""

        return await self.generate(prompt, enable_tools=False)
    
    async def generate_github_workflow(
        self, 
        project_info: Dict[str, Any],
        include_security_scan: bool = True,
        include_tests: bool = True,
    ) -> str:
        """Generate a GitHub Actions workflow."""
        prompt = f"""Generate a GitHub Actions workflow for CI/CD:

Project Info:
```json
{json.dumps(project_info, indent=2)}
```

Requirements:
- Trigger on push to main and pull requests
- Include build step
{'- Include security scanning step (placeholder for external security agent)' if include_security_scan else ''}
{'- Include test step' if include_tests else ''}
- Build and push Docker image to registry
- Deploy to Google Cloud Run
- Use GitHub secrets for sensitive values
- Include proper caching for faster builds

Return ONLY valid YAML, no explanations or markdown code blocks."""

        return await self.generate(prompt, enable_tools=False)
    
    async def generate_terraform(
        self, 
        project_info: Dict[str, Any],
        environment: str = "production"
    ) -> Dict[str, str]:
        """Generate Terraform configuration files."""
        prompt = f"""Generate Terraform configuration for deploying to Google Cloud Run:

Project Info:
```json
{json.dumps(project_info, indent=2)}
```

Environment: {environment}

Generate a JSON object with these keys, each containing the full file content:
- main_tf: main.tf content (provider, cloud run service, IAM)
- variables_tf: variables.tf content
- outputs_tf: outputs.tf content
- terraform_tfvars_example: terraform.tfvars.example content

Requirements:
- Use google provider with configurable project/region
- Cloud Run service with proper scaling settings
- IAM binding to allow unauthenticated access (or configurable)
- Output the service URL

Return ONLY valid JSON with the file contents."""

        response = await self.generate(prompt, enable_tools=False)
        
        try:
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1]
            if response.endswith("```"):
                response = response.rsplit("```", 1)[0]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse Terraform config as JSON")
            return {"raw_response": response}
    
    def start_chat(self) -> None:
        """Start a new chat session for multi-turn conversations."""
        tools = self._build_tools() if self.tools else None
        self.chat_session = self.model.start_chat(history=[])
    
    async def chat(self, message: str) -> str:
        """Send a message in an ongoing chat session."""
        if not self.chat_session:
            self.start_chat()
        
        response = self.chat_session.send_message(message)
        return self._extract_text(response)
