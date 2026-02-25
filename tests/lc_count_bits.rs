fn count_ones(mut n: i32) -> i32 {
    let mut count = 0;
    while n > 0 {
        count = count + n % 2;
        n = n / 2;
    }
    count
}

fn main() {
    println!("{}", count_ones(0));
    println!("{}", count_ones(11));
    println!("{}", count_ones(255));
}
