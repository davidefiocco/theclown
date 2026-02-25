fn trailing_zeroes(mut n: i32) -> i32 {
    let mut count = 0;
    while n >= 5 {
        n = n / 5;
        count = count + n;
    }
    count
}

fn main() {
    println!("{}", trailing_zeroes(5));
    println!("{}", trailing_zeroes(10));
    println!("{}", trailing_zeroes(25));
}
