fn is_power_of_two(mut n: i32) -> bool {
    if n <= 0 {
        return false;
    }
    while n % 2 == 0 {
        n = n / 2;
    }
    n == 1
}

fn main() {
    println!("{}", is_power_of_two(1));
    println!("{}", is_power_of_two(16));
    println!("{}", is_power_of_two(18));
}
