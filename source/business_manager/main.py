from services.sheets import get_urls
from services.sheets import guardar_ingresos as save_income
from services.calculations import calcular_dia as calculate_day


def main() -> None:
    responses = get_urls()

    if len(responses) != 3:
        raise RuntimeError("Could not read all three sheets.")

    results = calculate_day(responses[0], responses[1])

    for name, amount in results.items():
        print(f"{name}: {amount:.2f}")

    saved_rows = save_income(responses[0])
    print(f"Sales saved: {saved_rows}")


if __name__ == "__main__":
    main()