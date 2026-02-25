fn sum_of_squares(mut n: i32) -> i32 {
    let mut sum = 0;
    while n > 0 {
        let d = n % 10;
        sum = sum + d * d;
        n = n / 10;
    }
    sum
}

fn is_happy(n: i32) -> bool {
    let mut slow = n;
    let mut fast = sum_of_squares(n);
    while fast != 1 && slow != fast {
        slow = sum_of_squares(slow);
        fast = sum_of_squares(sum_of_squares(fast));
    }
    fast == 1
}

fn main() {
    println!("{}", is_happy(19));
    println!("{}", is_happy(2));
    println!("{}", is_happy(7));
}
