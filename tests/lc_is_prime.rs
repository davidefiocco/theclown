fn is_prime(n: i32) -> bool {
    if n < 2 {
        return false;
    }
    let mut i = 2;
    while i * i <= n {
        if n % i == 0 {
            return false;
        }
        i = i + 1;
    }
    true
}

fn main() {
    println!("{}", is_prime(1));
    println!("{}", is_prime(2));
    println!("{}", is_prime(17));
    println!("{}", is_prime(18));
}
