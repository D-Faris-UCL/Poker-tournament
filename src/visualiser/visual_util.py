def calculate_chip_denominations(total_chips: int) -> list[int]:
    """Calculate the chip denominations for a given total number of chips.
    
    Args:
        total_chips: The total number of chips to calculate the denominations for.
        
    Returns:
        A list of chip denominations.
    """
    chip_sizes = [500, 100, 50, 25, 5, 1]
    denominations = {size: 0 for size in chip_sizes}
    
    while total_chips > 0:
        for size in chip_sizes:
            if total_chips >= size:
                denominations[size] += 1
                total_chips -= size
                break
            
    denominations = {size: count for size, count in denominations.items() if count > 0}
            
    return denominations

if __name__ == "__main__":
    print(calculate_chip_denominations(1257))