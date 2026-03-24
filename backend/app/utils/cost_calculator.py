"""
Cost calculator for LLM API calls
Calculates cost based on model, input tokens, and output tokens
"""

def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_per_1m: dict
) -> float:
    """
    Calculate cost in USD for an LLM API call
    
    Args:
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cost_per_1m: Dictionary with cost per 1M tokens for each model
        
    Returns:
        Cost in USD
    """
    if model not in cost_per_1m:
        # If model not in cost table, estimate conservatively
        return 0.01
    
    input_cost = (input_tokens / 1_000_000) * cost_per_1m[model]["input"]
    output_cost = (output_tokens / 1_000_000) * cost_per_1m[model]["output"]
    
    return round(input_cost + output_cost, 6)