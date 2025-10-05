#!/usr/bin/env python3
import json
import os
import re
from pathlib import Path

def extract_bash_command_type(content):
    """
    Extract the first word from a bash code block.
    """
    # Find bash code block
    match = re.search(r'```bash\n(.*?)\n```', content, re.DOTALL)
    if match:
        command = match.group(1).strip()
        # Get the first word of the command
        first_word = command.split()[0] if command.split() else ""
        return first_word
    return None

def process_trajectory_file(traj_path, job_id):
    """
    Process a single trajectory JSON file and extract LLM calls and tool uses.
    Returns a trace entry in the format matching original_trace.jsonl.
    """
    with open(traj_path, 'r') as f:
        data = json.load(f)

    trace = []
    messages = data.get('messages', [])

    # Process messages to extract LLM calls and tool uses
    i = 0
    while i < len(messages):
        msg = messages[i]

        # Check if this is an assistant message (LLM response)
        if msg.get('role') == 'assistant':
            # Extract token counts from the response metadata
            extra = msg.get('extra', {})
            response = extra.get('response', {})
            usage = response.get('usage', {})

            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)

            # Parse the content to see if it contains a bash command (tool call)
            content = msg.get('content', '')
            tool_call_needed = "NO"

            # Check if there's a bash code block (indicates tool use)
            if '```bash' in content:
                # Extract the first word from bash command
                cmd_type = extract_bash_command_type(content)
                if cmd_type:
                    tool_call_needed = cmd_type

            if i + 1 == len(messages) - 1 and tool_call_needed != "NO":
                # If this is the last assistant message and there's a tool call,
                # we assume no execution result follows
                tool_call_needed = "NO"
            
            # Add LLM trace entry
            llm_entry = {
                "type": "llm",
                "input_token": input_tokens,
                "output_token": output_tokens,
                "tool_call_needed_next": tool_call_needed
            }
            trace.append(llm_entry)

            # If there's a tool call, check the next user message for execution results
            if tool_call_needed != "NO" and i + 1 < len(messages):
                next_msg = messages[i + 1]
                if next_msg.get('role') == 'user':
                    # This would contain the tool execution result
                    # Extract execution time if available
                    user_content = next_msg.get('content', '')

                    # Try to extract execution time from the content
                    execution_time = 1  # Default value
                    if '<execute_time>' in user_content:
                        try:
                            start = user_content.find('<execute_time>') + len('<execute_time>')
                            end = user_content.find('</execute_time>')
                            execution_time = int(float(user_content[start:end]) * 1000)  # Convert to ms
                        except:
                            execution_time = 1

                    # Add tool execution entry
                    tool_entry = {
                        "type": tool_call_needed,
                        "time": execution_time
                    }
                    trace.append(tool_entry)

        i += 1

    # Return the trace entry
    return {
        "request_id": str(job_id),
        "trace": trace
    }

def main():
    output_dir = Path('mini-swe-agent/output')

    # Get all subdirectories (job directories)
    job_dirs = sorted([d for d in output_dir.iterdir() if d.is_dir()])

    print(f"Found {len(job_dirs)} job directories")

    traces = []

    for idx, job_dir in enumerate(job_dirs, start=1):
        # Find the .traj.json file
        traj_files = list(job_dir.glob('*.traj.json'))

        if not traj_files:
            print(f"Warning: No trajectory file found in {job_dir.name}")
            continue

        traj_file = traj_files[0]

        try:
            trace_entry = process_trajectory_file(traj_file, idx)
            traces.append(trace_entry)

            if idx % 50 == 0:
                print(f"Processed {idx}/{len(job_dirs)} jobs...")
        except Exception as e:
            print(f"Error processing {traj_file}: {e}")
            continue

    # Write to swebench_trace.jsonl
    output_file = 'swebench_trace.jsonl'
    with open(output_file, 'w') as f:
        for trace in traces:
            f.write(json.dumps(trace) + '\n')

    print(f"\nGenerated {output_file} with {len(traces)} trace entries")

if __name__ == '__main__':
    main()
