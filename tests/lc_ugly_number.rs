fn is_ugly(mut n: i32) -> bool {
    if n <= 0 {
        return false;
    }
    while n % 2 == 0 {
        n = n / 2;
    }
    while n % 3 == 0 {
        n = n / 3;
    }
    while n % 5 == 0 {
        n = n / 5;
    }
    n == 1
}

fn main() {
    println!("{}", is_ugly(6));
    println!("{}", is_ugly(8));
    println!("{}", is_ugly(14));
    println!("{}", is_ugly(1));
}
