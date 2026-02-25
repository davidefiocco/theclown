fn gcd(mut a: i32, mut b: i32) -> i32 {
    while b != 0 {
        let t = b;
        b = a % b;
        a = t;
    }
    a
}

fn main() {
    println!("{}", gcd(12, 8));
    println!("{}", gcd(54, 24));
    println!("{}", gcd(17, 13));
}
