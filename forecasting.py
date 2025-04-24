import pandas as pd
import numpy as np
from statsmodels.tsa.arima.model import ARIMA
import plotly.graph_objects as go
from scipy.optimize import linprog
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import os
import sys
from datetime import datetime
import matplotlib.pyplot as plt

class MicronProductionPlanner:
    def __init__(self):
        self.products = []
        self.periods = []
        self.yielded_supply = {}
        self.on_hand = {}
        self.safety_stock_wos = {}
        self.effective_demand = {}
        self.seedstock = {}
        self.costs = {}
        self.supply = {}
        self.results = None
        self.excess_inventory = {}

    def ask_confirmation(self, message):
        while True:
            respuesta = input(f"{message} (Sí/No): ").strip().lower()
            if respuesta in ["sí", "si", "s", "yes", "y"]:
                return True
            elif respuesta in ["no", "n"]:
                return False
            else:
                print("Por favor, responde Sí o No.")


    def manual_input(self):
        print("\n" + "="*50)
        print(" RHINNON SYSTEM - PLANIFICACIÓN POR TRIMESTRE")
        print("="*50)

        num_products = int(input("¿Cuántos productos necesitas planificar? "))
        self.products = [input(f"Nombre del producto {i+1} (ej. Chip_AZ200): ") for i in range(num_products)]

        num_periods = int(input("\n¿Para cuántos trimestres deseas planificar? "))
        self.periods = [input(f"Nombre del trimestre {i+1} (ej. T1-2025): ") for i in range(num_periods)]

        print("\n Configuración Global para Optimización:")
        for product in self.products:
            self.costs[product] = float(input(f"Costo de producción para {product}: "))
            self.supply[product] = float(input(f"Suministro máximo para {product}: "))

        print("\n Ingresa los datos por trimestre:")
        for product in self.products:
            for period in self.periods:
                print(f"\n➡ Producto: {product} - {period}")
                self.yielded_supply[(product, period)] = float(input("Yielded Supply: "))
                self.on_hand[(product, period)] = float(input("On Hand (Finished Goods): "))
                self.safety_stock_wos[(product, period)] = float(input("Safety Stock Target (WOS): "))
                self.effective_demand[(product, period)] = float(input("Effective Demand: "))
                self.seedstock[(product, period)] = float(input("Seedstock: "))

    def input_data(self):
        if self.ask_confirmation("¿Deseas cargar los datos desde un archivo Excel?"):
            self.load_from_excel()
        else:
            self.manual_input()

    def load_from_excel(self):
        file_path = input("Ingresa el nombre del archivo Excel (incluyendo .xlsx): ")
        sheet_name = input("Nombre de la hoja (por ejemplo: Supply_Demand): ")
        df = pd.read_excel(file_path, sheet_name=sheet_name)

        self.products = df[df['Attribute'] == 'EffectiveDemand']['Product ID'].unique().tolist()
        self.periods = df.columns[2:].tolist()

        for _, row in df.iterrows():
            attr = row['Attribute']
            product = row['Product ID']

            for period in self.periods:
                value = row[period]

                if attr == "EffectiveDemand":
                    self.effective_demand[(product, period)] = value
                elif attr == "YieldedSupply":
                    self.yielded_supply[(product, period)] = value
                elif attr == "OnHand":
                    self.on_hand[(product, period)] = value
                elif attr == "SafetyStockTarget":
                    self.safety_stock_wos[(product, period)] = value
                elif attr == "Seedstock":
                    self.seedstock[(product, period)] = value
                elif attr == "Cost":
                    self.costs[product] = value
                elif attr == "MaxSupply":
                    self.supply[product] = value

        print("\n✅ Carga desde Excel completada.")

    def forecast_demand(self):
        forecasts = {}
        future_periods = 12  # Puedes ajustar este valor

        for product in self.products:
            try:
                series = [self.effective_demand[(product, period)] for period in self.periods if (product, period) in self.effective_demand]

                if len(series) < 2:
                    print(f"⚠ No hay suficientes datos para {product}. Se requieren al menos 2 periodos.")
                    continue

                model = ARIMA(series, order=(1, 1, 0))
                model_fit = model.fit()
                pred = model_fit.forecast(steps=future_periods)
                forecasts[product] = pred.tolist()

            # Gráfico
                plt.figure(figsize=(10, 4))
                periods_hist = self.periods
                periods_pred = [f"T+{i+1}" for i in range(future_periods)]
                plt.plot(periods_hist, series, label="Histórico", marker='o')
                plt.plot(periods_pred, pred, label="Pronóstico", marker='o', linestyle='--')
                plt.title(f"Demanda efectiva: {product}")
                plt.xlabel("Periodo")
                plt.ylabel("Unidades")
                plt.legend()
                plt.grid(True)
                plt.tight_layout()
                plt.savefig(f"forecast_{product}.png")
                plt.close()

                print(f"✔ Gráfico guardado como forecast_{product}.png")

            except Exception as e:
                print(f"⚠ Error generando ARIMA para {product}: {str(e)}")

    # Imprimir resultados (una sola vez por producto)
        print("\n--- Pronóstico (siguientes 12 trimestres) ---")
        for product in forecasts:
            print(f"\n📦 Producto: {product}")
            for i, pred in enumerate(forecasts[product], 1):
                print(f"  T+{i}: {pred:,.2f} unidades")

    # Exportar resultados a CSV (una sola vez)
        df_export = pd.DataFrame(forecasts)
        df_export.index = [f"T+{i+1}" for i in range(future_periods)]
        df_export.to_csv("forecast_results.csv")
        print("\n📁 Resultados exportados a 'forecast_results.csv'")

        return forecasts

    def run(self):
        self.input_data()
        self.forecast_demand()
        if self.ask_confirmation("\n¿Deseas ejecutar la optimización y generar reportes?"):
            if self.optimize_production():
                self.show_summary()
                if self.ask_confirmation("¿Deseas generar PDF con los gráficos y resultados?"):
                    img_files = self.generate_charts()
                    self.generate_pdf(img_files)
                    for img_file in img_files:
                        os.remove(img_file)

    # Métodos complementarios que ya estaban en tu sistema
    def calculate_metrics(self):
        weekly_demand = {}
        sst_units = {}
        sellable_supply = {}
        total_inventory = {}
        excess = {}

        for product in self.products:
            weekly_demand[product] = {}
            sst_units[product] = {}
            sellable_supply[product] = {}
            total_inventory[product] = {}
            excess[product] = {}

            for period in self.periods:
                weekly_demand[product][period] = self.effective_demand[(product, period)] / 13
                sst_units[product][period] = weekly_demand[product][period] * self.safety_stock_wos[(product, period)]
                sellable_supply[product][period] = self.on_hand[(product, period)] + self.yielded_supply[(product, period)]
                total_inventory[product][period] = sellable_supply[product][period] - self.effective_demand[(product, period)]
                excess[product][period] = total_inventory[product][period] - sst_units[product][period]

        return weekly_demand, sst_units, sellable_supply, total_inventory, excess

    def optimize_production(self):
        try:
            c = [self.costs[p] for p in self.products for _ in self.periods]

            A_ub = []
            b_ub = []
            for i, product in enumerate(self.products):
                constraint = [0] * len(c)
                for j in range(len(self.periods)):
                    constraint[i * len(self.periods) + j] = 1
                A_ub.append(constraint)
                b_ub.append(self.supply[product])

            for j, period in enumerate(self.periods):
                for i, product in enumerate(self.products):
                    constraint = [0] * len(c)
                    constraint[i * len(self.periods) + j] = -1
                    _, sst_units, _, _, _ = self.calculate_metrics()
                    b_ub.append(-(self.effective_demand[(product, period)] - sst_units[product][period] + self.seedstock[(product, period)]))
                    A_ub.append(constraint)

            result = linprog(c, A_ub=A_ub, b_ub=b_ub, method='highs')

            if result.success:
                self.results = result.x
                self.calculate_excess_inventory()
                print("\n✅ Optimización exitosa!")
                return True
            else:
                print("\n❌ No se encontró solución óptima. Revisa las restricciones.")
                return False

        except Exception as e:
            print(f"\n⚠ Error en optimización: {str(e)}")
            return False

    def calculate_excess_inventory(self):
        _, _, _, _, excess = self.calculate_metrics()
        self.excess_inventory = excess

    def show_summary(self):
        if self.results is None:
            return

        weekly_demand, sst_units, sellable_supply, total_inventory, excess = self.calculate_metrics()

        print("\n" + "="*50)
        print(" Resumen de Optimización")
        print("="*50)

        idx = 0
        for product in self.products:
            print(f"\n🔹 Producto: {product}")
            for period in self.periods:
                production = self.results[idx] if self.results else 0
                print(f"   {period}:")
                print(f"      → Yielded Supply: {self.yielded_supply[(product, period)]:.2f}")
                print(f"      → On Hand: {self.on_hand[(product, period)]:.2f}")
                print(f"      → Effective Demand: {self.effective_demand[(product, period)]:.2f}")
                print(f"      → Safety Stock (WOS): {self.safety_stock_wos[(product, period)]:.2f}")
                print(f"      → Weekly Demand: {weekly_demand[product][period]:.2f}")
                print(f"      → SST Units: {sst_units[product][period]:.2f}")
                print(f"      → Sellable Supply: {sellable_supply[product][period]:.2f}")
                print(f"      → Total Inventory: {total_inventory[product][period]:.2f}")
                print(f"      → Excess Inventory: {excess[product][period]:.2f}")
                print(f"      → Producción Óptima: {production:.2f}")
                idx += 1

    def generate_charts(self):
        img_files = []
        _, _, _, total_inventory, _ = self.calculate_metrics()

        for product in self.products:
            demand_values = [self.effective_demand[(product, period)] for period in self.periods]
            inventory_values = [total_inventory[product][period] for period in self.periods]

            plt.figure(figsize=(10, 5))
            plt.bar(self.periods, inventory_values, label='Inventario Total', color='lightblue')
            plt.plot(self.periods, demand_values, 'ro-', label='Demanda')
            plt.title(f'Planificación: {product}')
            plt.xlabel('Trimestres')
            plt.ylabel('Unidades')
            plt.legend()

            img_file = f"temp_chart_{product}.png"
            plt.savefig(img_file)
            plt.close()
            img_files.append(img_file)

        return img_files

    def generate_pdf(self, img_files):
        pdf_filename = "reporte_optimizacion.pdf"
        c = canvas.Canvas(pdf_filename, pagesize=letter)
        width, height = letter

        c.setFont("Helvetica-Bold", 16)
        c.drawString(100, height - 50, "Reporte de Optimización de Producción")
        c.setFont("Helvetica", 12)
        c.drawString(100, height - 70, f"Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

        y_position = height - 100
        c.setFont("Helvetica-Bold", 14)
        c.drawString(100, y_position, "Resultados por Producto")
        y_position -= 30

        _, _, _, total_inventory, excess = self.calculate_metrics()

        for i, product in enumerate(self.products):
            c.setFont("Helvetica-Bold", 12)
            c.drawString(100, y_position, f"Producto: {product}")
            y_position -= 20

            headers = ["Trimestre", "Demanda", "Inventario", "Exceso"]
            col_widths = [100, 100, 100, 100]

            x = 100
            for header, width in zip(headers, col_widths):
                c.drawString(x, y_position, header)
                x += width
            y_position -= 20

            for period in self.periods:
                x = 100
                demand = self.effective_demand[(product, period)]
                inventory = total_inventory[product][period]
                exc = excess[product][period]

                c.drawString(x, y_position, period)
                x += col_widths[0]
                c.drawString(x, y_position, f"{demand:.2f}")
                x += col_widths[1]
                c.drawString(x, y_position, f"{inventory:.2f}")
                x += col_widths[2]

                if exc < 0:
                    c.setFillColorRGB(1, 0, 0)
                else:
                    c.setFillColorRGB(0, 0.5, 0)

                c.drawString(x, y_position, f"{exc:.2f}")
                c.setFillColorRGB(0, 0, 0)

                y_position -= 20

            if i < len(img_files):
                c.drawImage(ImageReader(img_files[i]), 100, y_position - 150, width=400, height=200)
                y_position -= 170

            y_position -= 30
            if y_position < 150:
                c.showPage()
                y_position = height - 50

        c.save()
        print(f" Reporte PDF generado: {pdf_filename}")

if __name__ == "__main__":
    planner = MicronProductionPlanner()
    planner.run()
