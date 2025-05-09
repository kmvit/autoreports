
# Алгоритм действий пользователя с ролью Администратора (Подрядчика)

## 1. Регистрация и авторизация
1. Админ открывает бот в Telegram
2. Бот приветствует и предлагает авторизоваться
3. Админ вводит данные для авторизации с правами администратора
4. После успешной авторизации админ получает доступ к административной панели

## 2. Главное меню администратора
1. После авторизации администратор видит расширенное меню:
   - Управление заказчиками
   - Управление объектами
   - Управление персоналом
   - Управление техникой
   - Создать отчет
   - Просмотр отчетов
   - Направить отчет

## 3. Управление заказчиками
1. При выборе "Управление заказчиками" админ видит опции:
   - Список заказчиков
   - Добавить заказчика
   - Редактировать/удалить заказчика
2. При добавлении заказчика требуется указать:
   - Их логин в телеграмме
   - Их ключ доступа
   - ФИО
   - Наименование организации
   - Контактная информация
   - Список объектов, к которым предоставляется доступ

## 4. Управление объектами
1. При выборе "Управление объектами" админ видит опции:
   - Список объектов
   - Добавить новый объект
   - Редактировать объект
   - Удалить объект
2. При добавлении и редактировании объекта требуется указать:
   - Название объекта
   - Заказчик объекта

## 4. Управление персоналом
1. При выборе "Управление персоналом" админ видит опции:
   - Список ИТР
   - Добавить ИТР
   - Редактировать/удалить ИТР
   - Список рабочих
   - Добавить рабочего
   - Редактировать/удалить рабочего
2. При добавлении ИТР указывается:
   - ФИО
3. При добавлении рабочего указывается:
   - ФИО
   - Должность

## 5. Управление техникой
1. При выборе "Управление техникой" админ видит опции:
   - Список техники
   - Добавить технику
   - Редактировать/удалить технику
2. При добавлении техники указывается:
   - Наименование

## 6. Создание отчета
1. Админ выбирает "Создать отчет"
2. Бот запрашивает выбор объекта из списка
3. Выбирает тип работ
   - Инженерные коммуникации
     - Отопление
     - Водоснабжение и канализация
     - Пожаротушение
     - Вентиляция кондиционирование
     - Электроснабжение
     - Слаботочка
   - Внутриплощадочные сети:
     - НВК
     - Работы с ГНБ
     - ЭС
   - Благоустройство
   - Общестроительные работы:
     - Монолит
     - Устройство котлована
     - Демонтажные работы
     - Кладочные работы
     - Фасадные работы
     - Кровельные работы
     - Отделочные работы
4. Админ выбирает тип отчета:
   - Утренний отчет
   - Вечерний отчет
5. Админ выбирает действие:
   - Состав ИТР
   - Состав рабочих
   - Состав техники
   - Направить отчет
6. Админ добавляет состав ИТР для отчета:
   - Выбирает из списка существующих
7. Админ добавляет рабочих для отчета:
   - Выбирает из списка
8. Админ добавляет технику для отчета:
   - Выбирает из списка существующей техники
   - Указывает количество единиц техники
9. Админ добавляет фотоматериалы:
   - Выбирает фотографии из галереи
10. Админ добавляет комментарии к отчету:
    - Вводит комментарии
11. Админ нажимает "Сохранить отчет"
12. Отчет за текущий день(утро/вечер) сохраняется в системе
13. Админ видит сообщение о том, что отчет сохранен


## 7. Просмотр и управление отчетами
1. Админ выбирает "Мои отчеты"
2. Доступны фильтры:
   - По дате
   - По объекту
   - По ИТР
   - По типу отчета (Утро/Вечер)
   - По статусу (черновик, отправлен)
3. Админ может редактировать любой отчет даже после отправки
4. Админ может экспортировать отчеты в PDF или Excel


## 8. Направление отчетов
1. Админ направляет отчет заказчику
2. Заказчик получает отчет в Telegram
3. Заказчик может просмотреть отчет
4. Заказчик может скачать отчет в PDF или Excel


# Алгоритм действий пользователя с ролью Заказчика

## 1. Регистрация и авторизация
1. Заказчик открывает бот в Telegram
2. Бот приветствует и предлагает авторизоваться
3. Заказчик вводит данные для авторизации с правами заказчика

## 2. Главное меню заказчика
1. После авторизации заказчик видит основное меню:
   - История отчетов
   - Отчет за сегодня

3. При выборе "История отчетов" заказчик видит список отчетов:
   - По дате
   - По объекту
   - По типу отчета (Утро/Вечер)

4. При выборе "Отчет за сегодня" заказчик видит отчет за текущий день(утро/вечер)

## 3. Просмотр отчетов
1. Выбирает дату
2. Выбирает объект
3. Выбирает тип отчета (Утро/Вечер)
4. Бот показывает отчет
5. Заказчик может скачать отчет в PDF или Excel

