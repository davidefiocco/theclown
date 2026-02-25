fn sum_digits(mut n: i32) -> i32 {
    if n < 0 {
        n = 0 - n;
    }
    let mut sum = 0;
    while n > 0 {
        sum = sum + n % 10;
        n = n / 10;
    }
    sum
}

fn main() {
    println!("{}", sum_digits(12345));
    println!("{}", sum_digits(999));
    println!("{}", sum_digits(0));
}
