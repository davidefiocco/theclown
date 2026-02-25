fn reverse(mut n: i32) -> i32 {
    let negative = n < 0;
    if negative {
        n = 0 - n;
    }
    let mut result = 0;
    while n > 0 {
        result = result * 10 + n % 10;
        n = n / 10;
    }
    if negative { 0 - result } else { result }
}

fn main() {
    println!("{}", reverse(12345));
    println!("{}", reverse(-123));
    println!("{}", reverse(0));
}
