fn count_digits(mut n: i32) -> i32 {
    if n == 0 {
        return 1;
    }
    if n < 0 {
        n = 0 - n;
    }
    let mut count = 0;
    while n > 0 {
        count = count + 1;
        n = n / 10;
    }
    count
}

fn main() {
    println!("{}", count_digits(0));
    println!("{}", count_digits(12345));
    println!("{}", count_digits(-987));
}
