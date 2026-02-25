fn is_palindrome(n: i32) -> bool {
    if n < 0 {
        return false;
    }
    let mut rev = 0;
    let mut tmp = n;
    while tmp > 0 {
        rev = rev * 10 + tmp % 10;
        tmp = tmp / 10;
    }
    rev == n
}

fn main() {
    println!("{}", is_palindrome(12321));
    println!("{}", is_palindrome(12345));
    println!("{}", is_palindrome(0));
}
